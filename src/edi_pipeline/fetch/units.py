"""EPFL unit lookup by acronym via the EPFL search API.

Infoscience's `dc.description.sponsorship` gives unit codes (LIDIAP,
TRANSP-OR, ...) that are kept as the canonical identifiers; this lookup only
enriches them with the unit's full name and head.

Deliberately not used here: the current member list. Members come and go, and
for publication attribution we rely on the per-publication sponsorship (the
on-record affiliation at the moment of the publication) — never on a
researcher's current unit.
"""
from __future__ import annotations

import logging
import urllib.parse
from typing import Any

from edi_pipeline.cache import JsonlCache, get_json
from edi_pipeline.config import EPFL_SEARCH_API_URL

logger = logging.getLogger(__name__)


def fetch_unit(acronym: str, cache: JsonlCache | None = None) -> dict[str, Any] | None:
    """Look up one unit by its acronym (e.g. "TRANSP-OR").

    Returns {acronym, cf, name, unit_path, head} or None when the acronym is
    unknown. Not cached by default: names and heads can change, and the
    volume (hundreds of labs) is too small for caching to matter.
    """
    url = f"{EPFL_SEARCH_API_URL}?q={urllib.parse.quote(acronym)}"
    data = get_json(url, cache)

    if isinstance(data, dict):
        if not data or str(data.get("acronym") or "").upper() != acronym.upper():
            logger.warning("Unit lookup: no exact match for %r", acronym)
            return None
        return _normalize(data)

    if isinstance(data, list):
        # Prefix/substring queries return light entries {acronym, path, name}.
        # An exact hit among them cannot be re-queried (the API answers the
        # same list again), so the result stays light: name and path only,
        # without cf/head.
        for entry in data:
            if str(entry.get("acronym") or "").upper() == acronym.upper():
                return _normalize(entry)
    logger.warning("Unit lookup: no match for %r", acronym)
    return None


def fetch_units(
    acronyms: list[str], cache: JsonlCache | None = None
) -> dict[str, dict[str, Any] | None]:
    """Look up many unit acronyms; returns {acronym: unit or None}."""
    units: dict[str, dict[str, Any] | None] = {}
    for acronym in sorted(set(acronyms)):
        units[acronym] = fetch_unit(acronym, cache=cache)
    found = sum(1 for unit in units.values() if unit)
    logger.info("Unit lookup: %d/%d acronyms resolved", found, len(units))
    return units


def _normalize(unit: dict[str, Any]) -> dict[str, Any]:
    """Normalize a full unit dict or a light list entry to the same shape."""
    head = unit.get("head") or {}
    return {
        "acronym": unit.get("acronym"),
        "cf": str(unit["code"]) if unit.get("code") is not None else None,
        "name": unit.get("name"),
        "unit_path": [
            part.get("acronym") if isinstance(part, dict) else part
            for part in unit.get("path") or []
        ],
        "head": {
            "sciper": str(head["sciper"]) if head.get("sciper") is not None else None,
            "firstname": head.get("firstname"),
            "lastname": head.get("name"),
            "email": head.get("email"),
        } if head else None,
    }
