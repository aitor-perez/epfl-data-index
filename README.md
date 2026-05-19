# EPFL Data Index

**EPFL Data Index** is a Python library that makes it easy to manage, index and access EPFL documents in a shared OpenSearch index.

## Overview

This library exposes functions to create/delete indices, move aliases around, index/update/delete documents and several retrieval functions (full-text search, neural search, hybrid search, knn search, etc.).

Unstructured documents are ingested and given a minimal structure, then made readily available in a shared index. Embedding vectors are automatically computed from each document's `text` field using an external model from [RCP](https://www.epfl.ch/research/facilities/rcp/).

## Usage

To simply search documents
```
import epfl_data_index as edi

documents = edi.search(query="Perovskite solar cells")
```

To filter by document type
```
grants = edi.search(query="Perovskite solar cells", doc_type="grant")
```

To perform a knn search
```
grants = edi.knn(doc_id="person:123456", doc_type="grant")
```

To delete and recreate the index
```
edi.index()
```

TODO add more examples

## Setup

**Requirements:** Python ≥ 3.10, a running OpenSearch instance with an NLP ingest pipeline.

1. Install dependencies:
   ```bash
   pip install -e .
   ```

2. Create a `.env` file in the project root:
   ```env
   OPENSEARCH_USER=your_user
   OPENSEARCH_PASSWORD=your_password
   ```
