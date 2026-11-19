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
| `EDI_PIPELINE_CACHE_DIR` | `data/cache` | Folder of the yearly download cache (`edi_pipeline/download.py`). |
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

Fetch layer for publications and researchers from live sources (no source CSVs), plus the first merge step: reconciling Infoscience publications with OpenAlex works. Author disambiguation (via the external `setmatch` package), transforms and indexing are deferred. See *Planned pipeline* below.

- **http_client.py** — `get_json`, with retries on 403/429 and a polite delay between requests. A refusal's `Retry-After` header is obeyed; otherwise the waits grow up to 300 s. Infoscience answers 429 with `Retry-After: 900` (15 minutes), with or without a personal token, and it documents no limit: avoid bursts of quick requests, and run bulk downloads off-peak as its API page asks. It never caches; caching is done per year by `download.py`.
- **fetch/\_\_init\_\_.py** — Shared helpers: `normalize_doi` (bare, lowercase; applied to both sources) and `window_start(n)`, the lower date bound of the pipeline's window: 1 January, n calendar years before the current year (10 by default).
- **config.py** — API endpoints, page sizes and HTTP behaviour; optional credentials from env; yearly cache location (`EDI_PIPELINE_CACHE_DIR`, default `data/cache`) and maximum age (30 days).
- **download.py** — Downloads the window year by year (`download_infoscience`, `download_openalex_epfl`, both yielding raw records). The current year is always fetched fresh and never cached. Each past year is kept as `<cache_dir>/<source>/<year>.jsonl.gz` and read from there, unless the file is older than 30 days or `refresh=True` is passed, in which case that year is downloaded again. Past years are not frozen at the source (retrospective deposits, authors linked to a profile later, OpenAlex reprocessing), which is why the cache expires. A year's file appears only once that year is completely downloaded, so an interrupted run resumes from the years already done. `fetch_works_by_authors` is not cached: its result depends on each run's set of authors. Incremental harvesting through Infoscience's `lastModified` was considered and set aside: it cannot see deleted records, so full runs would still be needed.
- **fetch/infoscience.py** — EPFL publications since a date: `configuration=RELATION.OrgUnit.publications` scoped to the EPFL root OrgUnit, `dc.date.issued` range capped at today (forthcoming deposits with future dates are left out; OpenAlex is capped the same way), 100/page. Deliberately *not* filtered on `epfl.writtenAt` (retrospective deposits are kept; the value is captured as `written_at`) and *not* using `projection=preventMetadataSecurity` (it strips the `cris.virtual.*` fields). The download is slow, roughly 4 s per page (about 64,000 records for 10 years). `publications_of` keeps the records of given profiles locally, by authority UUID or sciper. `parse_publication` returns each author as `{name, sciper, authority}`. `authority` is the Infoscience person UUID, kept even when there is no sciper. The sciper is resolved by aligning that UUID with `cris.virtualsource.sciperId`/`cris.virtual.sciperId` (never by position in the author list, which gives wrong scipers: see the module docstring), or read from a pending link `will be referenced::SCIPER-ID::<sciper>`, which has no UUID. `parse_publication` also keeps `dc.description.sponsorship` for lab attribution (never `cris.virtual.department` — that reflects the author's *current* affiliation).
- **fetch/openalex.py** — Works with an EPFL-affiliated authorship since a date (`fetch_epfl_works`: `authorships.institutions.lineage:I5124864`, so EPFL's child institutions are included, all types by default, cursor paging at 200/page, yields lazily). Also works by DOI (OR-filter chunks of ≤100; the field name is written once, `doi:a|b`), works since a date by batches of ≤100 author IDs, with no EPFL affiliation required (`fetch_works_by_authors`, each work yielded once), author details, and `parse_work` (normalized DOI, rebuilt abstract, authors with `raw_author_name`, ORCID and an `is_epfl` flag that follows the same lineage rule). List endpoints truncate `authorships` at 100, so any work returned with 100 is re-fetched on its own to get the full author list (`complete_authorships`).
- **fetch/units.py** — Unit lookup by acronym via `https://search-api.epfl.ch/api/unit` (name, CF, path, head). Sponsorship unit codes stay canonical for publication attribution. The API's current member list is unused today; it is planned as the source of the researcher–unit relation (see *Planned pipeline*).
- **fetch/orcid.py** — sciper → ORCID map from EPFL's ORCID integration service (fetched, not yet consumed).
- **merge/publications.py** — One-to-one matching of Infoscience records and OpenAlex works: same DOI first, then same normalized title with agreeing authors (surname trigram overlap). Same-DOI pairs left out are reported as duplicates. Run by `scripts/reconcile_publications.py`, which downloads both sources (directly through the fetchers, without the yearly cache) into `data/` and writes `matches.csv` and `duplicates.csv`. Method and results: `src/edi_pipeline/docs/publication-reconciliation.md`.

Researchers are *not* fetched as profiles: they are derived from publication authors downstream, so a researcher appears only if they authored a publication since the cutoff date.

#### Planned pipeline (not yet implemented)

The goal is to use OpenAlex to recover researchers' history before they joined EPFL, which Infoscience barely covers for recent hires. Everything is limited to a window of whole calendar years, in every step and both sources: from 1 January ten years before the current year up to today (2016–2026 during 2026). The window only moves on 1 January, and every year but the current one is closed, which is what lets `download.py` cache past years. This replaces the approach `listeprof` used: there, OpenAlex author IDs were inferred from Infoscience DOIs and works were fetched over a fixed year window.

1. **Fetch** the window (2016–2026 during 2026) of Infoscience publications and of OpenAlex works affiliated with EPFL.
2. **Match publications** Infoscience ↔ OpenAlex with a fuzzy matcher that does not rely on DOI alone. Gaël owns it; the first version is `merge/publications.py`.
3. **Disambiguate authors** with `setmatch`, which groups author profiles from both sources into clusters.
4. **Keep sciper-anchored clusters**: a cluster is kept if it contains at least one Infoscience profile with a sciper, and then *all* its profiles are kept. For example, two Infoscience profiles (one with a sciper, one without) plus three OpenAlex profiles → all five are kept.
5. **Fetch every publication involving a kept profile**, still within the same window: from OpenAlex by batches of author IDs, which adds the works without an EPFL affiliation. Infoscience needs no second download: step 1 already holds all its records for the window, and `publications_of` selects those of the kept profiles. Then optionally re-run the fuzzy publication matcher to merge duplicates.
6. **Transform and index** Publication, Professor and Unit documents. Each publication carries `written_at` (Infoscience `epfl.writtenAt`: `"EPFL"`, or empty for retrospective deposits and OpenAlex-only works), so the index can be filtered on it. Records are downloaded whatever its value.

Implications for the current code:

- The fetchers for steps 1 and 5 exist (`fetch_publications_since`, `fetch_epfl_works`, `fetch_works_by_authors`, `publications_of`). Still missing on the fetch side: the search-api member lists.
- `fetch_works_by_dois` becomes secondary to the fuzzy matcher.
- The current member list from `fetch/units.py` (search-api) will now be used, for the researcher–unit relation below.

Two separate unit relations, recorded independently:

- **Publication → unit:** exactly as Infoscience records it (`dc.description.sponsorship`), when the publication is in Infoscience. Publications that exist only in OpenAlex, with no Infoscience match, have no units, and units are never inferred from authors. A publication's units can differ from all of its authors' units.
- **Researcher → unit:** current memberships, from the search-api member lists of research units. Only members who are kept researchers are linked; other staff in those units are ignored.

Scope assumptions: researchers are people with publications in Infoscience, and research units are units that appear in Infoscience sponsorship. We don't look people up by sciper, because every EPFL employee has a sciper and nothing tells researchers apart from other staff. Consequence: a researcher whose current unit has never sponsored a publication gets no researcher → unit link.

The two relations mean different things: where the work was attributed versus where the person is now. They are not expected to agree and must not be reconciled with each other.

Open questions:

- **Chained matches.** If clusters are joined through links, one wrong link can pull a namesake into a sciper's cluster, and step 5 then fetches all that person's works in the window. What should happen to a cluster that contains two scipers?
- **Output format of the fuzzy matcher.** For example, (Infoscience UUID, OpenAlex work ID, score) pairs.
- **After step 5.** Does `setmatch` need to run again? Co-authors who appear only in the new works are not kept.
- **Coverage.** Researchers with no EPFL-affiliated work in the window are not covered, and no publication from before the window is indexed.
- **Infoscience scope.** Step 1 searches under the EPFL root OrgUnit (63,823 records from 2016-11-19 to 2026-11-19, counted before the window moved to whole years). The unscoped search listeprof uses returns 66,041 for the same window. What the 2,218 extra records are has not been checked.

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
- `edi_pipeline` is not yet listed in `[tool.hatch.build.targets.wheel]` packages, so `pip install -e .` does not install it; import it with `PYTHONPATH=src` (or add it to the wheel packages). Pytest sets `pythonpath = ["src"]`, so `tests/test_edi_pipeline.py` works as is; those tests are offline, with HTTP monkeypatched.
