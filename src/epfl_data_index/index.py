import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import json

from opensearchpy import helpers

from epfl_data_index.client import get_client
from epfl_data_index.config import DEFAULT_INDEX_NAME
from epfl_data_index.models import Document

logger = logging.getLogger(__name__)

INDEX_CONFIG_PATH = Path(__file__).resolve().parents[2] / "index-config.json"


def create_index(index_name: Optional[str] = None):
    """Create (or recreate) the index using `index-config.json`.

    WARNING: This deletes the index if it already exists.
    """
    index_name = index_name or DEFAULT_INDEX_NAME
    client = get_client()
    if client.indices.exists(index=index_name):
        client.indices.delete(index=index_name)

    with open(INDEX_CONFIG_PATH, "r", encoding="utf-8") as f:
        index_body = json.load(f)

    client.indices.create(index=index_name, body=index_body)
    logger.info(f"Created index: {index_name}")


def index_documents(docs: list[Document], index_name: Optional[str] = None) -> None:
    """Index a list of Pydantic Document models in bulk.

    Documents must have `id`, `type`, `name` and `text` set. `created` and
    `updated` timestamps are always set by this function.
    """
    index_name = index_name or DEFAULT_INDEX_NAME

    now = datetime.now(timezone.utc).isoformat()

    actions = [
        {
            "_index": index_name,
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

    logger.info(f"Indexed {len(docs)} documents.")
