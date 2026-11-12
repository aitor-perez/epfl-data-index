"""Infoscience (DSpace-CRIS) search client — EPFL publications since a date.

Follows the Infoscience API best practices
(https://help-infoscience.epfl.ch/api.html#best-practices) and the guidance
of the Infoscience team:

- Publications are searched through the RELATION.OrgUnit.publications
  configuration scoped to the EPFL root OrgUnit, which covers the full unit
  hierarchy.
- `epfl.writtenAt` is captured on each record but NOT used as a search
  filter: publications written before the author joined EPFL (e.g. the past
  work of recently hired professors) are wanted too. Downstream code can
  filter on `written_at == "EPFL"` if ever needed.
- Page size 100 (the API maximum), polite delay between requests, URL-keyed
  JSONL cache so re-runs make no network calls.
- Labs are attributed via `dc.description.sponsorship`, which is traced on the
  record itself. Never `cris.virtual.department`: that virtual field is
  computed at request time from the author's *current* affiliation.
- No `projection=preventMetadataSecurity`: it silently strips the
  `cris.virtual.*` fields (verified live), which are needed to resolve author
  scipers.

Authors and their scipers come from the same records: `dc.contributor.author`
entries carry an `authority` (person UUID) matching a value in
`cris.virtualsource.sciperId`; the aligned `cris.virtual.sciperId` entry holds
that person's sciper. Unlinked authors (no authority) are external.

Researchers are NOT fetched separately: they are derived from publication
authors downstream, so a researcher only appears if they authored a
publication since the cutoff date.
"""
from __future__ import annotations

import logging
import re
import urllib.parse
from typing import Any, Iterator

from edi_pipeline.cache import JsonlCache, get_json
from edi_pipeline.config import (
    INFOSCIENCE_BASE_URL,
    INFOSCIENCE_PAGE_SIZE,
    INFOSCIENCE_TOKEN,
)

logger = logging.getLogger(__name__)

SEARCH_URL = f"{INFOSCIENCE_BASE_URL}/discover/search/objects"

# Recommended pattern from the Infoscience team: OrgUnit-scoped publication
# search. Any OrgUnit UUID works as scope (e.g. a faculty); the EPFL root
# covers the whole school.
PUB_CONFIGURATION = "RELATION.OrgUnit.publications"
EPFL_SCOPE_UUID = "41674f42-ba15-4612-9817-2a6f60985c01"
PUB_SORT = "dc.date.issued,DESC"

# Sentinel value Infoscience puts in empty virtual fields.
PLACEHOLDER = "#PLACEHOLDER_PARENT_METADATA_VALUE#"


def _headers() -> dict[str, str]:
    """Anonymous access covers public metadata; bearer token only if set."""
    if INFOSCIENCE_TOKEN:
        return {"Authorization": f"Bearer {INFOSCIENCE_TOKEN}"}
    return {}


def search_objects(
    configuration: str,
    query: str | None = None,
    scope: str | None = None,
    sort: str | None = None,
    cache: JsonlCache | None = None,
    max_records: int | None = None,
    page_size: int = INFOSCIENCE_PAGE_SIZE,
) -> Iterator[dict[str, Any]]:
    """Yield every indexableObject matching the search, paging automatically."""
    page, total_pages, yielded = 0, 1, 0
    while page < total_pages:
        params: dict[str, Any] = {"configuration": configuration, "size": page_size, "page": page}
        if query:
            params["query"] = query
        if scope:
            params["scope"] = scope
        if sort:
            params["sort"] = sort
        url = f"{SEARCH_URL}?{urllib.parse.urlencode(params)}"
        data = get_json(url, cache, headers=_headers())
        result = data.get("_embedded", {}).get("searchResult", {})
        total_pages = result.get("page", {}).get("totalPages", 1)
        for obj in result.get("_embedded", {}).get("objects", []):
            item = obj.get("_embedded", {}).get("indexableObject")
            if item is None:
                continue
            yield item
            yielded += 1
            if max_records is not None and yielded >= max_records:
                return
        page += 1
        logger.info(
            "infoscience %s: page %d/%d (%d records)", configuration, page, total_pages, yielded
        )


def fetch_publications_since(
    since: str, cache: JsonlCache | None = None, max_records: int | None = None
) -> Iterator[dict[str, Any]]:
    """Yield raw EPFL publications issued since `since` ("YYYY-MM-DD" or "YYYY").

    EPFL-wide (root OrgUnit scope), newest first, retrospective deposits
    included. Use `parse_publication` to extract fields and authors.

    Note: this selects by issue date. For incremental harvesting of *changed*
    records, the documented field is `lastModified` (updates + new deposits).
    """
    query = f"dc.date.issued:[{since} TO *]"
    return search_objects(
        PUB_CONFIGURATION,
        query=query,
        scope=EPFL_SCOPE_UUID,
        sort=PUB_SORT,
        cache=cache,
        max_records=max_records,
    )


# ---------------------------------------------------------------------------
# record parsing
# ---------------------------------------------------------------------------

def _first(md: dict[str, Any], field: str) -> str | None:
    entries = md.get(field)
    if not entries:
        return None
    value = entries[0].get("value")
    return None if value in (None, "", PLACEHOLDER) else str(value)


def _values(md: dict[str, Any], field: str) -> list[dict[str, Any]]:
    """Metadata entries with a usable value (placeholder/empty dropped)."""
    return [e for e in md.get(field, []) if e.get("value") not in (None, "", PLACEHOLDER)]


def _sciper_by_authority(md: dict[str, Any]) -> dict[str, str]:
    """Person UUID -> sciper, from the aligned cris.virtual* arrays."""
    return {
        source.get("value"): entry.get("value")
        for source, entry in zip(
            md.get("cris.virtualsource.sciperId", []),
            md.get("cris.virtual.sciperId", []),
        )
        if source.get("value") and entry.get("value") not in (None, "", PLACEHOLDER)
    }


def parse_publication(item: dict[str, Any]) -> dict[str, Any]:
    """Extract publication + authors (with scipers) from a raw search item.

    `authors` keeps record order; `sciper` is None for external authors (no
    authority link). `sponsorship` lists the on-record unit/funding
    attributions (lab short codes such as "LIDIAP") — the field the
    Infoscience team recommends for lab-level attribution. `written_at` is
    "EPFL" when the record is marked as written at EPFL, None otherwise
    (retrospective deposits) — captured, never filtered, at fetch time.
    """
    md = item.get("metadata", {})
    issued = _first(md, "dc.date.issued") or ""
    match = re.search(r"(19|20)\d{2}", issued)
    sciper_map = _sciper_by_authority(md)

    authors = [
        {
            "name": str(entry["value"]),
            "sciper": sciper_map.get(entry.get("authority")),
        }
        for entry in _values(md, "dc.contributor.author")
    ]
    return {
        "uuid": item["uuid"],
        "title": _first(md, "dc.title"),
        "abstract": _first(md, "dc.description.abstract"),
        "doi": _first(md, "dc.identifier.doi"),
        "year": int(match.group(0)) if match else None,
        "url": _first(md, "dc.identifier.uri"),
        "last_modified": item.get("lastModified"),
        "written_at": _first(md, "epfl.writtenAt"),
        "sponsorship": [str(e["value"]) for e in _values(md, "dc.description.sponsorship")],
        "authors": authors,
    }
