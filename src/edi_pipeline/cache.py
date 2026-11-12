"""Append-only JSONL download cache and a shared JSON GET helper.

The cache is keyed by full URL: a second run with unchanged inputs makes no
network calls. Corrupt lines (e.g. truncated writes) are skipped — a lost
entry costs one refetch, not the run.
"""
from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any

import requests

from edi_pipeline.config import POLITE_DELAY_SECONDS, REQUEST_TIMEOUT, WAIT_ON_RETRY

logger = logging.getLogger(__name__)

USER_AGENT = "edi_pipeline/0.1"


class JsonlCache:
    """Append-only JSONL store: one self-describing record per entry."""

    def __init__(self, path: Path, key_field: str):
        self.path = path
        self.key_field = key_field
        self.records: dict[str, dict[str, Any]] = {}
        if path.exists():
            with path.open("r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        record = json.loads(line)
                        self.records[record[key_field]] = record
                    except (json.JSONDecodeError, KeyError, TypeError):
                        continue

    def put(self, record: dict[str, Any]) -> None:
        self.records[record[self.key_field]] = record
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")


def get_json(
    url: str, cache: JsonlCache | None = None, headers: dict[str, str] | None = None
) -> Any:
    """GET a JSON URL, serving from and writing to the URL-keyed cache.

    Retries transient failures (403/429 from rate limiting, network errors)
    with the delays from WAIT_ON_RETRY.
    """
    if cache is not None:
        hit = cache.records.get(url)
        if hit is not None:
            return hit["data"]

    last_error: Exception | None = None
    for attempt in range(len(WAIT_ON_RETRY) + 1):
        try:
            response = requests.get(
                url,
                headers={"accept": "application/json", "User-Agent": USER_AGENT, **(headers or {})},
                timeout=REQUEST_TIMEOUT,
            )
            if response.status_code in (403, 429) and attempt < len(WAIT_ON_RETRY):
                wait = WAIT_ON_RETRY[attempt]
                logger.warning("HTTP %s for %s — retrying in %ss", response.status_code, url, wait)
                time.sleep(wait)
                continue
            response.raise_for_status()
            data = response.json()
            if cache is not None:
                cache.put({"url": url, "data": data})
            time.sleep(POLITE_DELAY_SECONDS)  # be polite to the APIs
            return data
        except requests.RequestException as error:
            last_error = error
            if attempt < len(WAIT_ON_RETRY):
                time.sleep(WAIT_ON_RETRY[attempt])
    raise RuntimeError(f"GET {url} failed after retries: {last_error}")
