# AGENTS.md — EPFL Data Index

## Quick Reference

| Item | Value |
|------|-------|
| Language | Python 3.11+ |
| Build tool | Hatchling (`pip install -e .`) |
| Package | `src/epfl_data_index` |
| Author | Aitor Pérez <aitor.perez@epfl.ch> |

## Build & Run

```bash
# Install in editable mode
pip install -e .

# Required env vars (set in `.env`):
# EDI_OPENSEARCH_HOST, EDI_OPENSEARCH_PORT, EDI_OPENSEARCH_USER, EDI_OPENSEARCH_PASSWORD
# EDI_OPENSEARCH_INDEX_NAME, EDI_OPENSEARCH_EMBEDDING_MODEL_ID
```

## Architecture

- **client.py** — `get_client()` returns a configured `opensearchpy.OpenSearch` instance (SSL, no cert verify).
- **config.py** — A thin `_Config` class that reads all settings from environment variables via `os.environ.get(key)`.
- **models.py** — Pydantic models: `Document` base class, `Publication`, `Professor`, `Unit`, plus nested variants for many-to-many relations.
- **search.py** — Public API surface (`search`, `fetch_all`). `search` performs neural (embedding) search over `text` field. `fetch_all` uses point-in-time (PIT) pagination.
- **index.py** — Index management (`create_index`, `index_documents`) and embedding updates (averaging publication vectors for professors/units).
- **load.py** — Fetches CSVs from an internal SQL API, normalizes data, returns lists of Pydantic models.

## OpenSearch Details

- **Index config**: `index-config.json` in repo root.
- **Pipeline**: `nlp-ingest-pipeline` must exist on the cluster (declared as `default_pipeline`).
- **Vector field**: `embedding` is `knn_vector`, 4096 dims, `l2` space.
- **Dynamic mapping**: Strings map to `text` with a `keyword` subfield (`ignore_above: 256`).

## Conventions

- All env var keys in `config.py` are **uppercase** and prefixed with `EDI_`.
- Document IDs are namespaced: `publication:<id>`, `professor:<sciper>`, `unit:<cf>`.
- `text` field is the canonical field for embedding and full-text search; it is assembled manually in `load.py`.
- The package `__init__.py` only exports `search` and `fetch_all`. Anything else (`index`, `knn`) is used via direct import or CLI scripts.

## Common Tasks

- **Add a new doc type**: Add a Pydantic model in `models.py` inheriting from `Document`, then update `load.py` to hydrate instances, and `index.py` to index them.
- **Change embedding behavior**: Edit `index-config.json` (dimension, space_type) and the `embed()` call in `search.py`.
- **Add search variants**: Put new query DSL builders in `search.py` and expose in `__init__.py` if public.

## Notes

- `index.py` has hard-coded `INDEX_NAME` / `MODEL_ID` locals—update them when switching environments.
- No test suite exists yet. Verify changes by running scripts directly (`python -m epfl_data_index.search`).
- `load.py` hits an internal EPFL endpoint (`itsisa0052.xaas.epfl.ch:5001`)—scripts will fail outside the EPFL network.
