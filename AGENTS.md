# AGENTS.md — EPFL Data Index

## Quick Reference

| Item | Value |
|------|-------|
| Language | Python 3.11+ |
| Build tool | Hatchling (`pip install -e .`) |
| Package | `src/epfl_data_index` |
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
| `EDI_OPENSEARCH_EMBEDDING_MODEL_ID` | `1qybAp4BjzNfTND26ePS` | OpenSearch text-embedding model ID. |
| `EDI_OPENSEARCH_INDEX_NAME` | `test` | Default index name used when `index_name` is not passed explicitly. |

## Architecture

- **client.py** — `get_client()` returns a configured `opensearchpy.OpenSearch` instance (SSL, no cert verify).
- **config.py** — A thin `_Config` class that reads required settings from environment variables. Optional variables are listed in `OPTIONAL_ENV_DEFAULTS` and fall back to their default values when not set.
- **models/** — Pydantic models: `Document` base class, `Publication`, `Professor`, `Unit`, plus nested variants for many-to-many relations. `Document` requires `id`, `type`, `name` and `text`.
- **search.py** — Public API surface (`search`, `fetch_all`, `knn`, `embed`). `search` performs neural (embedding) search over the `text` field and returns a list of source dicts (including `_score`). `fetch_all` uses point-in-time (PIT) pagination and returns a list of source dicts. `knn` finds nearest neighbors by document ID and returns a list of source dicts (including `_score`). `search`, `fetch_all` and `knn` accept `include_text` and `include_embeddings` flags (both default to `False`) to avoid returning heavy fields.
- **index.py** — Index management (`create_index`, `index_documents`). Documents are indexed once with the `text` field defined by `scripts/load.py`; the cluster's default ingest pipeline computes the embedding from that text.
- **scripts/load.py** — Fetches CSVs from an internal SQL API, normalizes data, returns lists of Pydantic models.

## OpenSearch Details

- **Index config**: `index-config.json` in repo root.
- **Pipeline**: `nlp-ingest-pipeline` must exist on the cluster (declared as `default_pipeline`).
- **Vector field**: `embedding` is `knn_vector`, 4096 dims, `l2` space.
- **Dynamic mapping**: Strings map to `text` with a `keyword` subfield (`ignore_above: 256`).

## Conventions

- All env var keys in `config.py` are **uppercase** and prefixed with `EDI_`.
- Document IDs are namespaced: `publication:<id>`, `professor:<sciper>`, `unit:<cf>`.
- `text` field is the canonical field for embedding and full-text search; it is assembled manually in `load.py`.
- The package `__init__.py` exports `search`, `fetch_all`, `knn`, `embed`, and `index_documents`.

## Common Tasks

- **Add a new doc type**: Add a Pydantic model in `models/` inheriting from `Document`, then update `scripts/load.py` to hydrate instances, and index them with `index_documents`.
- **Change embedding behavior**: Edit `index-config.json` (dimension, space_type) and the `embed()` call in `search.py`.
- **Add search variants**: Put new query DSL builders in `search.py` and expose in `__init__.py` if public.

## Notes

- All search and index functions accept an optional `index_name` parameter; they default to the value of `EDI_OPENSEARCH_INDEX_NAME` (or `"test"` if it is not set).
- Run tests with `python -m pytest tests/`.
- Reindex core documents with `python scripts/reindex.py`.
- `scripts/load.py` hits an internal EPFL endpoint (`itsisa0052.xaas.epfl.ch:5001`)—scripts will fail outside the EPFL network.
