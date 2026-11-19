"""EPFL unit lookup by acronym via the EPFL search API.

Infoscience's `dc.description.sponsorship` gives unit codes (LIDIAP,
TRANSP-OR, ...) that are kept as the canonical identifiers; this lookup
enriches them with the unit's full name and head.

Two unit relations, kept separate (see AGENTS.md, *Planned pipeline*):

- publication → unit comes from the per-publication sponsorship only (the
  on-record attribution), never from a researcher's current unit;
- researcher → unit comes from the API's current member list (`members`),
  restricted to the pipeline's researchers by `units_by_member`.

The API lists the people of a unit that has no sub-units, in practice a lab.
A larger unit (a faculty, an institute) comes with its sub-units instead.
"""
from __future__ import annotations

import logging
import urllib.parse
from typing import Any, Iterable

from edi_pipeline.config import EPFL_SEARCH_API_URL
from edi_pipeline.http_client import get_json

logger = logging.getLogger(__name__)


def fetch_unit(acronym: str) -> dict[str, Any] | None:
    """Look up one unit by its exact acronym (e.g. "TRANSP-OR").

    Returns {acronym, cf, name, unit_path, head, members} or None when the
    acronym is unknown (a unit that was renamed or closed, or a sponsorship
    code that is not an EPFL unit). `members` is the unit's current people,
    each as {sciper, firstname, lastname, position}, or None for a unit that
    only has sub-units (see module docstring).
    """
    # `acro` is the exact lookup. `q` is a search: for an acronym that is also
    # the beginning of others ("LAI"), it answers a list of matches without details.
    data = get_json(f"{EPFL_SEARCH_API_URL}?acro={urllib.parse.quote(acronym)}")
    if not isinstance(data, dict) or str(data.get("acronym") or "").upper() != acronym.upper():
        logger.info("Unit lookup: %r is not a current EPFL unit", acronym)
        return None
    return _normalize(data)


def fetch_units(acronyms: list[str]) -> dict[str, dict[str, Any] | None]:
    """Look up many unit acronyms; returns {acronym: unit or None}."""
    units: dict[str, dict[str, Any] | None] = {}
    for acronym in sorted(set(acronyms)):
        units[acronym] = fetch_unit(acronym)
    found = sum(1 for unit in units.values() if unit)
    logger.info("Unit lookup: %d/%d acronyms resolved", found, len(units))
    return units


def _normalize(unit: dict[str, Any]) -> dict[str, Any]:
    """Keep the fields the pipeline uses from a unit as returned by the API."""
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
        "members": [
            {
                "sciper": str(person["sciper"]),
                "firstname": person.get("firstname"),
                "lastname": person.get("name"),
                "position": person.get("position"),
            }
            for person in unit["people"] if person.get("sciper") is not None
        ] if "people" in unit else None,
    }


def units_by_member(
    units: dict[str, dict[str, Any] | None], scipers: Iterable[str]
) -> dict[str, list[dict[str, Any]]]:
    """Researcher → unit links: {sciper: [{acronym, cf, name, position}, ...]}.

    `units` is the result of `fetch_units`. Only the given scipers are
    linked (the pipeline's kept researchers); other staff of the units are
    ignored, and a researcher who is in none of the units is absent from the
    result.
    """
    wanted = {str(sciper) for sciper in scipers}
    links: dict[str, list[dict[str, Any]]] = {}
    for unit in units.values():
        for member in (unit or {}).get("members") or []:
            if member["sciper"] in wanted:
                links.setdefault(member["sciper"], []).append({
                    "acronym": unit["acronym"],
                    "cf": unit["cf"],
                    "name": unit["name"],
                    "position": member["position"],
                })
    return links
