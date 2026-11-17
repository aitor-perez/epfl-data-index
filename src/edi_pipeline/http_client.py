"""Shared JSON GET helper used by every fetcher.

No caching: the pipeline always works on fresh data, so every run hits the
live APIs. Transient failures (403/429 from rate limiting, network errors)
are retried with the delays from WAIT_ON_RETRY, and every successful request
is followed by a short polite pause.
"""
from __future__ import annotations

import logging
import time
from typing import Any

import requests

from edi_pipeline.config import POLITE_DELAY_SECONDS, REQUEST_TIMEOUT, WAIT_ON_RETRY

logger = logging.getLogger(__name__)

USER_AGENT = "edi_pipeline/0.1"


def get_json(url: str, headers: dict[str, str] | None = None) -> Any:
    """GET a JSON URL, retrying transient failures; raises after the last retry."""
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
            time.sleep(POLITE_DELAY_SECONDS)  # be polite to the APIs
            return data
        except requests.RequestException as error:
            last_error = error
            if attempt < len(WAIT_ON_RETRY):
                time.sleep(WAIT_ON_RETRY[attempt])
    raise RuntimeError(f"GET {url} failed after retries: {last_error}")
