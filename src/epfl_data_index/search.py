from typing import Optional, Union

from epfl_data_index.client import get_client
from epfl_data_index.config import CONFIG


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


def fetch_all(doc_type: Optional[Union[str, list[str]]] = None):
    client = get_client()
    if not doc_type:
        doc_type = []
    elif isinstance(doc_type, str):
        doc_type = [doc_type]

    if doc_type:
        query = {"terms": {"type": doc_type}}
    else:
        query = {"match_all": {}}

    size = client.count(index=CONFIG["EDI_OPENSEARCH_INDEX_NAME"], body={"query": query})["count"]

    # We need to paginate if size > page_size
    page_size = 500
    needs_pagination = size > page_size

    body = {
        "_source": {"includes": ["id", "type", "name", "text", "embedding"]},
        "size": page_size if needs_pagination else size,
        "query": query,
        "sort": [{"_id": "asc"}],
    }

    # Point-in-time pagination
    pit_id = client.create_pit(index=CONFIG["EDI_OPENSEARCH_INDEX_NAME"], keep_alive="5m")["pit_id"]
    body["pit"] = {"id": pit_id, "keep_alive": "5m"}
    all_hits = []

    try:
        remaining = size
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


def search(query: Union[str, list[str]], doc_type: Optional[Union[str, list[str]]] = None, size: int = 10):
    client = get_client()
    if isinstance(query, str):
        query = [query]

    if not doc_type:
        doc_type = []
    elif isinstance(doc_type, str):
        doc_type = [doc_type]

    body = {
        "_source": {"includes": ["id", "type", "name", "text", "embedding"]},
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

    if doc_type:
        body["query"]["bool"]["filter"] = [{"terms": {"type": doc_type}}]

    return client.search(index=CONFIG["EDI_OPENSEARCH_INDEX_NAME"], body=body)


if __name__ == "__main__":
    from dotenv import load_dotenv

    load_dotenv()

    # r = search(text='robotics', doc_type='publication')
    # for hit in r["hits"]["hits"]:
    #     print(hit["_source"])

    publications = fetch_all(doc_type='publication')

    print(publications)
