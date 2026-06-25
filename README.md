# EPFL Data Index

**EPFL Data Index** is a Python library that makes it easy to manage, index and access EPFL documents in a shared OpenSearch index.

## Overview

This library exposes functions to create/delete indices, move aliases around, index/update/delete documents and several retrieval functions (full-text search, neural search, hybrid search, knn search, etc.).

Unstructured documents are ingested and given a minimal structure, then made readily available in a shared index. Embedding vectors are automatically computed from each document's `text` field using an external model from [RCP](https://www.epfl.ch/research/facilities/rcp/).

## Usage

```python
import epfl_data_index as edi
```

### Search

```python
docs = edi.search("machine learning in healthcare")
grants = edi.search("machine learning", type="grant")
```

### Fetch all documents of a type

```python
publications = edi.fetch_all(type="publication")
```

### k-NN search

```python
neighbors = edi.knn(id="unit:123", type="publication", size=20)
```

### Retrieve heavy fields

By default `search`, `fetch_all` and `knn` exclude the `text` and `embedding` fields from results. Pass `include_text=True` and/or `include_embeddings=True` to retrieve them:

```python
docs = edi.fetch_all(type="publication", include_text=True, include_embeddings=True)
```

### Index your own documents

```python
from typing import Literal, Optional
from epfl_data_index.models import Document

class RCOrganization(Document):
    type: Literal["rc_organization"] = "rc_organization"
    zip: Optional[str] = None

orgs = [
    RCOrganization(
        id="rc_organization:CHE-123.456.789",
        name="ABC SA",
        text="A company based in Lausanne...",
        zip="1001",
    ),
]
edi.index_documents(orgs)
```

All search and index functions accept an optional `index_name` argument. If omitted, they default to `"test"`.

## Setup

**Requirements:** Python ≥ 3.11, a running OpenSearch instance with an NLP ingest pipeline.

### Install from GitLab

The repository is open within EPFL's GitLab. Most users can install it directly from the Git URL without cloning:

```bash
pip install git+ssh://git@gitlab-ssh.epfl.ch/p-data/epfl-data-index.git
```

Pin to a tag or branch for reproducibility:

```bash
pip install git+ssh://git@gitlab-ssh.epfl.ch/p-data/epfl-data-index.git@v0.1.0
```

### Editable install for developers

If you plan to modify the code, clone the repository and install in editable mode:

```bash
git clone git@gitlab-ssh.epfl.ch:p-data/epfl-data-index.git
cd epfl-data-index
pip install -e .
```

### Test dependencies (optional)

```bash
pip install -e ".[test]"
```

### Environment variables

Create a `.env` file in the project root:

```env
EDI_OPENSEARCH_HOST=your_host
EDI_OPENSEARCH_PORT=9200
EDI_OPENSEARCH_USER=your_user
EDI_OPENSEARCH_PASSWORD=your_password
EDI_OPENSEARCH_EMBEDDING_MODEL_ID=your_model_id
```

## Reindex core documents

To recreate the index and reload publications, professors, and units from the internal EPFL API:

```bash
python scripts/reindex.py
```

## Running tests

```bash
python -m pytest tests/
```
