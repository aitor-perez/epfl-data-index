from datetime import datetime, timezone
from pathlib import Path

import json

from opensearchpy import helpers

from epfl_data_index.client import get_client
from epfl_data_index.config import CONFIG
from epfl_data_index.models import Document
from epfl_data_index.load import load_all

INDEX_CONFIG_PATH = Path(__file__).resolve().parents[2] / "index-config.json"

INDEX_NAME = CONFIG["EDI_OPENSEARCH_INDEX_NAME"]


def create_index():
    client = get_client()
    if client.indices.exists(index=INDEX_NAME):
        client.indices.delete(index=INDEX_NAME)

    with open(INDEX_CONFIG_PATH, "r", encoding="utf-8") as f:
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
    for ok, info in bulk:
        if not ok:
            raise Exception(f"Indexing failed: {info}")

    print(f"Indexed {len(docs)} documents.")


if __name__ == "__main__":
    from dotenv import load_dotenv

    load_dotenv()

    publications, professors, units = load_all()

    create_index()
    index_documents(publications + professors + units)
