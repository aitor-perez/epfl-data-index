# AGENTS.md — EPFL Data Index

## Quick Reference

| Item | Value |
|------|-------|
| Language | Python 3.11+ |
| Build tool | Hatchling (`pip install -e .`) |
| Packages | `src/epfl_data_index` (OpenSearch index) · `src/edi_pipeline` (live data retrieval) |
| Author | Aitor Pérez <aitor.perez@epfl.ch> |

## Build & Run

### Users (install from GitLab)

The repository is open within EPFL's GitLab. Install the package directly from the Git URL:

```bash
pip install git+ssh://git@gitlab-ssh.epfl.ch/p-data/epfl-data-index.git
```

Pin to a tag or branch for reproducibility:

```bash
pip install git+ssh://git@gitlab-ssh.epfl.ch/p-data/epfl-data-index.git@v0.1.0
```

### Developers (editable install)

Clone the repository and install in editable mode:

```bash
git clone git@gitlab-ssh.epfl.ch:p-data/epfl-data-index.git
cd epfl-data-index
pip install -e .
```

### Required environment variables

Set these in a `.env` file or in your shell:

```env
EDI_OPENSEARCH_HOST=your_host
EDI_OPENSEARCH_PORT=9200
EDI_OPENSEARCH_USER=your_user
EDI_OPENSEARCH_PASSWORD=your_password
```

### Optional environment variables

| Variable | Default | Description |
|----------|---------|-------------|
| `EDI_OPENSEARCH_EMBEDDING_MODEL_ID` | `77D-56ABnEX0QP_uqWw7` | OpenSearch text-embedding model ID. |
| `EDI_OPENSEARCH_INDEX_NAME` | `shared_test_260928` | Default index name used when `index_name` is not passed explicitly. |
| `EDI_PIPELINE_OPENALEX_API_KEY` or `API_KEY_OPENALEX` | — | OpenAlex API key used by `edi_pipeline` (`edi_pipeline/config.py`). |
| `INFOSCIENCE_TOKEN` | — | Optional Infoscience bearer token; anonymous access already covers public metadata. |

## Architecture

- **client.py** — `get_client()` returns a configured `opensearchpy.OpenSearch` instance (SSL, no cert verify).
- **config.py** — A thin `_Config` class that reads required settings from environment variables. Optional variables are listed in `OPTIONAL_ENV_DEFAULTS` and fall back to their default values when not set.
- **models/** — Pydantic models: `Document` base class, `Publication`, `Professor`, `Unit`, `Grant`, `EUCall`, plus nested variants for many-to-many relations. `Document` requires `id`, `type`, `name` and `text`. Recent additions: `Professor.orcid` and `Professor.is_professor` (non-professor researchers are also indexed, under type `professor`), and `Publication.written_at` (Infoscience `epfl.writtenAt`: `"EPFL"` or `None` for retrospective deposits).
- **search.py** — Public API surface (`search`, `fetch_all`, `knn`, `embed`). `search` performs neural (embedding) search over the `text` field and returns a list of source dicts (including `_score`). `fetch_all` uses point-in-time (PIT) pagination and returns a list of source dicts. `knn` finds nearest neighbors by document ID and returns a list of source dicts (including `_score`). `search`, `fetch_all` and `knn` accept `include_text` and `include_embeddings` flags (both default to `False`) to avoid returning heavy fields.
- **index.py** — Index management (`create_index`, `index_documents`). Documents are indexed once with the `text` field defined by the loader scripts; the cluster's default ingest pipeline computes the embedding from that text.
- **scripts/load_prof_api.py** — Fetches CSVs from an internal SQL API (professors, publications, units), normalizes data, returns lists of Pydantic models.
- **scripts/load_grants.py** — Loads grants from the Tableau API (requires the external `tableau_api` repo).
- **scripts/load_eu_calls.py** — Loads EU calls from a local CSV (`data/eu_calls.csv`).

### edi_pipeline — live data retrieval (`src/edi_pipeline/`)

Fetch layer for publications and researchers from live sources (no source CSVs), plus the first merge step: reconciling Infoscience publications with OpenAlex works. Author disambiguation (via the external `setmatch` package), transforms and indexing are deferred.

- **cache.py** — Append-only JSONL cache keyed by full URL (re-runs make no network calls) and `get_json` with retries on 403/429 and a polite delay between requests.
- **config.py** — API endpoints, page sizes and HTTP behaviour; optional credentials from env.
- **fetch/infoscience.py** — EPFL publications since a date: `configuration=RELATION.OrgUnit.publications` scoped to the EPFL root OrgUnit, `dc.date.issued` range, 100/page. Deliberately *not* filtered on `epfl.writtenAt` (retrospective deposits are kept; the value is captured as `written_at`) and *not* using `projection=preventMetadataSecurity` (it strips the `cris.virtual.*` fields). `parse_publication` resolves author scipers via the author `authority` UUID aligned with `cris.virtualsource.sciperId`/`cris.virtual.sciperId`, and keeps `dc.description.sponsorship` for lab attribution (never `cris.virtual.department` — that reflects the author's *current* affiliation).
- **fetch/openalex.py** — Works by DOI (OR-filter chunks of ≤100, misses cached as negatives), all EPFL works in a date range (`fetch_epfl_works`: `authorships.institutions.lineage` filter, so EPFL's child institutions are included), works by author (cursor paging), author details, abstract reconstruction from OpenAlex's inverted index.
- **fetch/units.py** — Unit lookup by acronym via `https://search-api.epfl.ch/api/unit` (name, CF, path, head). Enrichment only: sponsorship unit codes stay canonical, and the API's current member list is deliberately unused.
- **fetch/orcid.py** — sciper → ORCID map from EPFL's ORCID integration service (fetched, not yet consumed).
- **merge/publications.py** — One-to-one matching of Infoscience records and OpenAlex works: same DOI first, then same normalized title with agreeing authors (surname trigram overlap). Same-DOI pairs left out are reported as duplicates. Run by `scripts/reconcile_publications.py`, which downloads both sources into `data/` and writes `matches.csv` and `duplicates.csv`. Method and results: `src/edi_pipeline/docs/publication-reconciliation.md`.

Researchers are *not* fetched as profiles: they are derived from publication authors downstream, so a researcher appears only if they authored a publication since the cutoff date.

## OpenSearch Details

- **Index config**: `index-config.json` in repo root.
- **Pipeline**: `nlp-ingest-pipeline` must exist on the cluster (declared as `default_pipeline`).
- **Vector field**: `embedding` is `knn_vector`, 4096 dims, `l2` space.
- **Dynamic mapping**: Strings map to `text` with a `keyword` subfield (`ignore_above: 256`).

## Conventions

- All env var keys in `config.py` are **uppercase** and prefixed with `EDI_`.
- Document IDs are namespaced: `publication:<id>`, `professor:<sciper>`, `unit:<cf>`.
- `text` field is the canonical field for embedding and full-text search; it is assembled manually in each loader script (`build_text` helpers).
- The package `__init__.py` exports `search`, `fetch_all`, `knn`, `embed`, and `index_documents`.

## Common Tasks

- **Add a new doc type**: Add a Pydantic model in `models/` inheriting from `Document`, then update the relevant loader script in `scripts/` to hydrate instances, and index them with `index_documents`.
- **Change embedding behavior**: Edit `index-config.json` (dimension, space_type) and the `embed()` call in `search.py`.
- **Add search variants**: Put new query DSL builders in `search.py` and expose in `__init__.py` if public.

## Notes

- All search and index functions accept an optional `index_name` parameter; they default to the value of `EDI_OPENSEARCH_INDEX_NAME` (or `shared_test_260928` if it is not set).
- Run tests with `python -m pytest tests/`.
- Reindex core documents with `python scripts/reindex.py`.
- `scripts/load_prof_api.py` hits an internal EPFL endpoint (`itsisa0052.xaas.epfl.ch:5001`)—scripts will fail outside the EPFL network.
- `edi_pipeline` is not yet listed in `[tool.hatch.build.targets.wheel]` packages, so `pip install -e .` does not install it; import it with `PYTHONPATH=src` (or add it to the wheel packages).
