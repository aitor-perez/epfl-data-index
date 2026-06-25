from typing import Optional, Union

from epfl_data_index.client import get_client
from epfl_data_index.config import CONFIG, DEFAULT_INDEX_NAME


def _normalize_doc_type(doc_type: Optional[Union[str, list[str]]]) -> list[str]:
    if not doc_type:
        return []
    if isinstance(doc_type, str):
        return [doc_type]
    return doc_type


def embed(texts: list[str]) -> list[list[float]]:
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
    include_embeddings: bool = False,
    index_name: Optional[str] = None,
):
    client = get_client()
    type = _normalize_doc_type(type)
    index_name = index_name or DEFAULT_INDEX_NAME

    if type:
        query = {"terms": {"type": type}}
    else:
        query = {"match_all": {}}

    total = client.count(index=index_name, body={"query": query})["count"]

    source_fields = ["id", "type", "name", "text"]
    if include_embeddings:
        source_fields.append("embedding")

    body = {
        "_source": {"includes": source_fields},
        "query": query,
        "sort": [{"_id": "asc"}],
    }

    # Small result set: single regular search, no PIT needed
    if total <= page_size:
        body["size"] = total
        return client.search(index=index_name, body=body)

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

    # Update response and return
    response["hits"]["hits"] = all_hits
    response["hits"]["total"] = {"value": len(all_hits), "relation": "eq"}

    return response


def search(
    query: Union[str, list[str]],
    type: Optional[Union[str, list[str]]] = None,
    size: int = 10,
    include_embeddings: bool = False,
    index_name: Optional[str] = None,
):
    client = get_client()
    if isinstance(query, str):
        query = [query]

    type = _normalize_doc_type(type)
    index_name = index_name or DEFAULT_INDEX_NAME

    source_fields = ["id", "type", "name", "text"]
    if include_embeddings:
        source_fields.append("embedding")

    body = {
        "_source": {"includes": source_fields},
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

    return client.search(index=index_name, body=body)


def knn(
    id: str,
    type: Optional[Union[str, list[str]]] = None,
    size: int = 10,
    include_embeddings: bool = False,
    index_name: Optional[str] = None,
):
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

    source_fields = ["id", "type", "name", "text"]
    if include_embeddings:
        source_fields.append("embedding")

    body = {
        "_source": {"includes": source_fields},
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

    return client.search(index=index_name, body=body)


if __name__ == "__main__":
    from dotenv import load_dotenv

    load_dotenv()

    results = fetch_all(type='publication')
    print(f"Fetched {len(results['hits']['hits'])} publications")
