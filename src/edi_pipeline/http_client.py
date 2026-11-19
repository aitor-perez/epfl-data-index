"""Shared JSON GET helper used by every fetcher.

No caching here: every call hits the live API. Closed calendar years are
cached one level up, by `edi_pipeline.download`. Transient failures (403/429
from rate limiting, network errors) are retried, and every successful request
is followed by a short polite pause.

When a refusal carries a `Retry-After` header, that wait is obeyed instead of
the delays from WAIT_ON_RETRY. Infoscience answers 429 with `Retry-After: 900`
(15 minutes); retrying sooner is refused again.
"""
from __future__ import annotations

import logging
import time
from typing import Any

import requests

from edi_pipeline.config import (
    MAX_RETRY_AFTER_SECONDS,
    POLITE_DELAY_SECONDS,
    REQUEST_TIMEOUT,
    RETRY_AFTER_MARGIN_SECONDS,
    WAIT_ON_RETRY,
)

logger = logging.getLogger(__name__)

USER_AGENT = "edi_pipeline/0.1"


def _retry_wait(response: requests.Response, attempt: int) -> float:
    """Seconds to wait before retrying a refused request."""
    retry_after = response.headers.get("Retry-After", "")
    if retry_after.isdigit():
        return min(int(retry_after), MAX_RETRY_AFTER_SECONDS) + RETRY_AFTER_MARGIN_SECONDS
    return WAIT_ON_RETRY[attempt]


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
                wait = _retry_wait(response, attempt)
                logger.warning("HTTP %s for %s — retrying in %.0fs", response.status_code, url, wait)
                time.sleep(wait)
                continue
            if 400 <= response.status_code < 500:
                # A malformed or unauthorized request stays so: fail now instead of retrying for minutes.
                raise RuntimeError(f"GET {url} failed: HTTP {response.status_code} {response.text[:200]}")
            response.raise_for_status()
            data = response.json()
            time.sleep(POLITE_DELAY_SECONDS)  # be polite to the APIs
            return data
        except requests.RequestException as error:
            last_error = error
            if attempt < len(WAIT_ON_RETRY):
                time.sleep(WAIT_ON_RETRY[attempt])
    raise RuntimeError(f"GET {url} failed after retries: {last_error}")
