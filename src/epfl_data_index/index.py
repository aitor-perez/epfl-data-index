from datetime import datetime, timezone

import json

import numpy as np

from opensearchpy import helpers

from client import get_client
from models import Document, Professor, Unit
from load import load_all

INDEX_NAME = "test"


def create_index():
    client = get_client()
    if client.indices.exists(index=INDEX_NAME):
        client.indices.delete(index=INDEX_NAME)

    with open(f"../../index-config.json", "r", encoding="utf-8") as f:
        index_body = json.load(f)

    client.indices.create(index=INDEX_NAME, body=index_body)
    print(f"Created index: {INDEX_NAME}")


def index_documents(docs: list[Document]):
    now = datetime.now(timezone.utc).isoformat()

    actions = [
        {
            "_index": INDEX_NAME,
            "_id": doc.id,
            "_source": doc.model_dump(exclude={"created", "updated"}) | {"created": now, "updated": now},
        }
        for doc in docs
    ]

    bulk = helpers.parallel_bulk(
        get_client(),
        actions,
        thread_count=5,
        chunk_size=32,
        request_timeout=300,
    )

    # Need to consume the generator for calls to run
    for _ in bulk:
        pass

    print(f"Indexed {len(docs)} documents.")


def _average_embeddings(doc_ids: list[str]) -> list[float] | None:
    client = get_client()
    if not doc_ids:
        return None

    response = client.mget(index=INDEX_NAME, body={"ids": doc_ids}, _source_includes=["embedding"])
    vectors = [
        hit["_source"]["embedding"]
        for hit in response["docs"]
        if hit.get("found") and "embedding" in hit.get("_source", {})
    ]

    if not vectors:
        return None

    avg = np.mean(vectors, axis=0)
    norm = np.linalg.norm(avg)
    if norm == 0:
        return None
    return (avg / norm).tolist()


def update_embeddings(professors: list[Professor], units: list[Unit]):
    client = get_client()
    for prof in professors:
        vector = _average_embeddings([p.id for p in prof.publications])
        if vector:
            client.update(index=INDEX_NAME, id=prof.id, body={"doc": {"embedding": vector}})

    print(f"Updated embeddings for {len(professors)} professors.")

    for unit in units:
        vector = _average_embeddings([p.id for p in unit.publications])
        if vector:
            client.update(index=INDEX_NAME, id=unit.id, body={"doc": {"embedding": vector}})

    print(f"Updated embeddings for {len(units)} units.")


if __name__ == "__main__":
    from dotenv import load_dotenv

    load_dotenv()

    publications, professors, units = load_all()

    create_index()
    index_documents(publications + professors + units)
    # update_embeddings(professors, units)

    # index_documents(professors + units)
    # update_embeddings(professors, units)
