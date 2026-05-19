import requests
from opensearchpy import OpenSearch

from config import CONFIG

INDEX_NAME = "test2"
MODEL_ID = "41_9BZ0BrpQLIV_1Av_A"

client = OpenSearch(
    hosts=[{"host": "localhost", "port": 9200}],
    http_auth=(CONFIG["OPENSEARCH_USER"], CONFIG["OPENSEARCH_PASSWORD"]),
    use_ssl=True,
    verify_certs=False,
    ssl_show_warn=False,
)


def _fetch_openalex_titles(query: str, n: int = 10) -> list[str]:
    resp = requests.get(
        "https://api.openalex.org/works",
        params={"search": query, "per-page": n, "api-key": CONFIG["OPENALEX_API_KEY"]},
    )
    resp.raise_for_status()
    return [r["display_name"] for r in resp.json()["results"] if r.get("display_name")]


def _cut_tail(hits: list, min_gap_ratio: float = 0.2, min_score_ratio: float = 0.05, absolute_threshold: float = 0.4) -> list:
    if not hits:
        return hits

    scores = [h["_score"] for h in hits]
    top = scores[0]

    # Absolute threshold
    hits = [h for h in hits if h["_score"] >= absolute_threshold]

    # Largest consecutive gap (if significant)
    gaps = [scores[i] - scores[i + 1] for i in range(len(scores) - 1)]
    max_gap = max(gaps)
    if max_gap >= top * min_gap_ratio:
        return hits[:gaps.index(max_gap) + 1]

    # Relative threshold
    threshold = top * min_score_ratio
    return [h for h in hits if h["_score"] >= threshold]


def search(text: str, size: int = 100, hyde: bool = False, rerank: bool = False) -> dict:
    """
    Search function.

    size   — number of results to return.
    hyde   — expand the query using OpenAlex paper titles as proxy queries (HyDE variant).
    rerank — re-score results with the cross-encoder reranker pipeline.
    """

    if hyde:
        titles = _fetch_openalex_titles(text)

        print(titles)

        query = {
            "dis_max": {
                "queries": [
                    {
                        "neural": {
                            "embedding": {
                                "query_text": title,
                                "model_id": MODEL_ID,
                                "k": size,
                            }
                        }
                    }
                    for title in titles
                ]
            }
        }

        kwargs = {"request_timeout": 600}
    else:
        query = {
            "neural": {
                "embedding": {
                    "query_text": text,
                    "model_id": MODEL_ID,
                    "k": size,
                }
            }
        }

        kwargs = {}

    body = {
        "_source": {"excludes": ["embedding"]},
        "query": query,
        "size": size,
    }

    if rerank:
        body["ext"] = {"rerank": {"query_context": {"query_text": text}}}
        kwargs["search_pipeline"] = "reranker_pipeline"

    resp = client.search(index=INDEX_NAME, body=body, **kwargs)

    return resp


if __name__ == "__main__":
    import matplotlib.pyplot as plt

    query = "machine learning applied to healthcare"

    resp = search(query, size=10, hyde=True, rerank=True)
    hits = resp["hits"]["hits"]
    scores = [h["_score"] for h in hits]

    plt.figure(figsize=(12, 4))
    plt.plot(scores, marker="o", markersize=3)
    plt.xlabel("Rank")
    plt.ylabel("Score")
    plt.title(f'Score distribution — "{query}"')
    plt.tight_layout()
    plt.savefig("scores.png", dpi=150)
    print("\nPlot saved to scores.png")

    # resp["hits"]["hits"] = _cut_tail(resp["hits"]["hits"])

    print(f"Returned {len(hits)} hits:")
    for h in hits:
        print(f"  {h['_score']:.4f}  {h['_source']['id']}  {h['_source'].get('name', '')[:60]}")
