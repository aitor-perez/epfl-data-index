from typing import Optional, Union

from epfl_data_index.client import get_client
from epfl_data_index.config import CONFIG, DEFAULT_INDEX_NAME


def _normalize_doc_type(doc_type: Optional[Union[str, list[str]]]) -> list[str]:
    if not doc_type:
        return []
    if isinstance(doc_type, str):
        return [doc_type]
    return doc_type


def _source_filter(include_text: bool, include_embeddings: bool) -> dict:
    excludes = []
    if not include_text:
        excludes.append("text")
    if not include_embeddings:
        excludes.append("embedding")
    return {"excludes": excludes}


def embed(texts: list[str]) -> list[list[float]]:
    """Compute embedding vectors for a list of texts using the configured model."""
    client = get_client()
    response = client.plugins.ml.predict(
        algorithm_name="text_embedding",
        model_id=CONFIG["EDI_OPENSEARCH_EMBEDDING_MODEL_ID"],
        body={
            "text_docs": texts,
            "target_response": ["sentence_embedding"]
        }
    )

    results = []
    for i, r in enumerate(response.get("inference_results", [])):
        if r.get("status_code") != 200 or "output" not in r or not r["output"]:
            raise RuntimeError(f"Embedding inference failed for text at index {i}: {r}")
        results.append(r["output"][0]["data"])

    return results


def fetch_all(
    type: Optional[Union[str, list[str]]] = None,
    page_size: int = 500,
    include_text: bool = False,
    include_embeddings: bool = False,
    index_name: Optional[str] = None,
) -> list[dict]:
    """Return all documents as a list of source dicts, optionally filtered by type.

    By default the heavy `text` and `embedding` fields are excluded from the
    returned source. Set `include_text` and/or `include_embeddings` to True to
    retrieve them.
    """
    client = get_client()
    type = _normalize_doc_type(type)
    index_name = index_name or DEFAULT_INDEX_NAME

    if type:
        query = {"terms": {"type": type}}
    else:
        query = {"match_all": {}}

    total = client.count(index=index_name, body={"query": query})["count"]

    body = {
        "_source": _source_filter(include_text, include_embeddings),
        "query": query,
        "sort": [{"_id": "asc"}],
    }

    # Small result set: single regular search, no PIT needed
    if total <= page_size:
        body["size"] = total
        response = client.search(index=index_name, body=body)
        return [hit["_source"] for hit in response["hits"]["hits"]]

    # Large result set: point-in-time pagination
    body["size"] = page_size
    pit_id = client.create_pit(index=index_name, keep_alive="5m")["pit_id"]
    body["pit"] = {"id": pit_id, "keep_alive": "5m"}
    all_hits = []

    try:
        remaining = total
        while True:
            # Fetch next batch
            body["size"] = min(page_size, remaining)
            response = client.search(body=body)  # no index= when using PIT

            # Break if no hits
            hits = response["hits"]["hits"]
            if not hits:
                break

            # Store new hits
            all_hits.extend(hits)

            # Refresh pit_id
            pit_id = response.get("pit_id", pit_id)
            body["pit"]["id"] = pit_id
            body["search_after"] = hits[-1]["sort"]

            # Update remaining documents
            remaining -= len(hits)

            # Break if no more documents
            if remaining <= 0 or len(hits) < body["size"]:
                break
    finally:
        # Clear pit
        client.delete_pit(body={"pit_id": pit_id})

    return [hit["_source"] for hit in all_hits]


def search(
    query: Union[str, list[str]],
    type: Optional[Union[str, list[str]]] = None,
    size: int = 10,
    include_text: bool = False,
    include_embeddings: bool = False,
    index_name: Optional[str] = None,
) -> list[dict]:
    """Run a neural search and return a list of matching document source dicts.

    `query` can be a single string or a list of strings; multiple strings are
    combined with a `bool.should` clause. Use `type` to restrict results to one
    or more document types.

    By default `text` and `embedding` are excluded from returned sources; set
    `include_text` and/or `include_embeddings` to retrieve them.
    """
    client = get_client()
    if isinstance(query, str):
        query = [query]

    type = _normalize_doc_type(type)
    index_name = index_name or DEFAULT_INDEX_NAME

    body = {
        "_source": _source_filter(include_text, include_embeddings),
        "size": size,
        "query": {
            "bool": {
                "should": [
                    {
                        "neural": {
                            "embedding": {
                                "query_text": q,
                                "model_id": CONFIG["EDI_OPENSEARCH_EMBEDDING_MODEL_ID"],
                                "k": size,
                            }
                        }
                    }
                    for q in query
                ]
            }
        },
    }

    if type:
        body["query"]["bool"]["filter"] = [{"terms": {"type": type}}]

    response = client.search(index=index_name, body=body)
    return [hit["_source"] for hit in response["hits"]["hits"]]


def knn(
    id: str,
    type: Optional[Union[str, list[str]]] = None,
    size: int = 10,
    include_text: bool = False,
    include_embeddings: bool = False,
    index_name: Optional[str] = None,
) -> list[dict]:
    """Find the k nearest neighbours of a reference document and return them as
    a list of source dicts.

    The reference document must already have an `embedding` stored in the index.
    Use `type` to restrict neighbours to specific document types.

    By default `text` and `embedding` are excluded from returned sources; set
    `include_text` and/or `include_embeddings` to retrieve them.
    """
    client = get_client()
    type = _normalize_doc_type(type)
    index_name = index_name or DEFAULT_INDEX_NAME

    # Fetch the embedding of the reference document
    source = client.get(index=index_name, id=id, _source_includes=["embedding"])
    embedding = source["_source"].get("embedding")
    if not embedding:
        raise ValueError(f"Document {id} has no embedding")

    # Optionally restrict to specific document types
    filter_clauses = []
    if type:
        filter_clauses.append({"terms": {"type": type}})

    body = {
        "_source": _source_filter(include_text, include_embeddings),
        "size": size,
        "query": {
            "bool": {
                "must": {
                    "knn": {
                        "embedding": {
                            "vector": embedding,
                            "k": size,
                        }
                    }
                },
                "must_not": {"term": {"_id": id}},
                "filter": filter_clauses,
            }
        },
    }

    response = client.search(index=index_name, body=body)
    return [hit["_source"] for hit in response["hits"]["hits"]]


if __name__ == "__main__":
    from dotenv import load_dotenv

    load_dotenv()

    results = fetch_all(type='publication')
    print(f"Fetched {len(results)} publications")
