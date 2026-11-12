"""Sciper -> ORCID lookup from EPFL's ORCID integration service."""
from __future__ import annotations

import logging

import requests

from edi_pipeline.config import ORCID_INTEGRATION_URL, REQUEST_TIMEOUT

logger = logging.getLogger(__name__)


def fetch_orcid_map() -> dict[str, str]:
    """Return {sciper: orcid}. Best effort: logs a warning, never raises."""
    try:
        response = requests.get(ORCID_INTEGRATION_URL, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        data = response.json()
    except (requests.RequestException, ValueError) as error:
        logger.warning("Could not fetch ORCID integration data: %s", error)
        return {}

    orcid_map = {}
    for sciper, entry in data.items():
        orcid = (entry or {}).get("orcid")
        if sciper.isdigit() and orcid:
            orcid_map[sciper] = orcid
    logger.info("ORCID integration: %d scipers with ORCID", len(orcid_map))
    return orcid_map
