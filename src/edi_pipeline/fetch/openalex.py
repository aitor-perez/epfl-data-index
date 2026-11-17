"""OpenAlex works and authors client.

List endpoints return at most AUTHORSHIP_CAP authorships per work. Any work
that comes back with that many is re-fetched on its own (the single-work
endpoint returns the full list), so callers always get complete author lists.
"""
from __future__ import annotations

import logging
import urllib.parse
from datetime import date
from typing import Any, Iterator

from edi_pipeline.config import (
    EPFL_OPENALEX_ID,
    OPENALEX_API_KEY,
    OPENALEX_BASE_URL,
    OPENALEX_CHUNK_SIZE,
    OPENALEX_PER_PAGE,
    OPENALEX_TYPES,
)
from edi_pipeline.fetch import normalize_doi
from edi_pipeline.http_client import get_json

logger = logging.getLogger(__name__)

# Fields needed for publication matching, author matching and new records.
WORK_FIELDS = (
    "id,doi,title,publication_year,publication_date,type,authorships,abstract_inverted_index"
)

# List endpoints truncate `authorships` to this many entries.
AUTHORSHIP_CAP = 100


def _url(path: str, **params: Any) -> str:
    if OPENALEX_API_KEY:
        params["api_key"] = OPENALEX_API_KEY
    return f"{OPENALEX_BASE_URL}/{path}?{urllib.parse.urlencode(params)}"


def _short_id(openalex_id: str) -> str:
    """https://openalex.org/W123 -> W123 (bare IDs pass through)."""
    return openalex_id.rstrip("/").rsplit("/", 1)[-1]


def fetch_work(openalex_id: str) -> dict[str, Any] | None:
    """One work by ID, with its full author list; None if the request fails."""
    try:
        return get_json(_url(f"works/{_short_id(openalex_id)}", select=WORK_FIELDS))
    except RuntimeError as error:
        logger.warning("openalex work %s: %s", openalex_id, error)
        return None


def complete_authorships(work: dict[str, Any]) -> dict[str, Any]:
    """Replace a possibly truncated author list with the full one (in place).

    A list result with exactly AUTHORSHIP_CAP authorships may have been
    truncated. The rare work with exactly 100 real authors costs one extra
    request, which is cheaper than missing authors on the others.
    """
    if len(work.get("authorships") or []) >= AUTHORSHIP_CAP:
        full = fetch_work(work["id"])
        if full and full.get("authorships"):
            logger.info(
                "openalex work %s: author list completed (%d -> %d)",
                _short_id(work["id"]), len(work["authorships"]), len(full["authorships"]),
            )
            work["authorships"] = full["authorships"]
    return work


def _iter_works(filter_: str, max_records: int | None = None) -> Iterator[dict[str, Any]]:
    """Yield every work matching `filter_` (cursor paging, complete author lists)."""
    cursor: str | None = "*"
    yielded = 0
    while cursor:
        data = get_json(_url(
            "works", filter=filter_, select=WORK_FIELDS,
            cursor=cursor, **{"per-page": OPENALEX_PER_PAGE},
        ))
        for work in data.get("results", []):
            yield complete_authorships(work)
            yielded += 1
            if max_records is not None and yielded >= max_records:
                return
        cursor = data.get("meta", {}).get("next_cursor")
        logger.info(
            "openalex works [%s]: %d/%s", filter_, yielded, data.get("meta", {}).get("count"),
        )


def fetch_epfl_works(
    since: str,
    until: str | None = None,
    types: str | None = None,
    max_records: int | None = None,
) -> Iterator[dict[str, Any]]:
    """Yield works with an EPFL-affiliated authorship, published between `since` and `until`.

    `since`/`until` are "YYYY-MM-DD"; `until` defaults to today, which leaves
    out works with a future publication date. For "at most 10 years old",
    pass `fetch.since_years_ago(10)`. EPFL is matched on the institution itself
    (`authorships.institutions.id`), not its OpenAlex lineage, which also
    pulls in child entities such as the joint EPFL/ETH Swiss Data Science
    Center. `types` is an OpenAlex type filter ("article|book"); None keeps
    all types, the closest match to Infoscience's coverage.
    """
    parts = [
        f"authorships.institutions.id:{EPFL_OPENALEX_ID}",
        f"from_publication_date:{since}",
        f"to_publication_date:{until or date.today().isoformat()}",
    ]
    if types:
        parts.append(f"type:{types}")
    return _iter_works(",".join(parts), max_records=max_records)


def fetch_works_by_dois(dois: list[str]) -> dict[str, dict[str, Any] | None]:
    """Fetch works for the given DOIs, chunked by the OR-filter cap.

    Returns {doi: work or None}, None meaning "not on OpenAlex". DOIs are
    normalized (bare, lowercase) on both sides.
    """
    clean = sorted({d for d in (normalize_doi(doi) for doi in dois) if d})
    works: dict[str, dict[str, Any] | None] = {}
    for start in range(0, len(clean), OPENALEX_CHUNK_SIZE):
        chunk = clean[start:start + OPENALEX_CHUNK_SIZE]
        # The filter name once, then pipe-separated values: repeating "doi:"
        # per value reads as an OR between filters, which OpenAlex rejects.
        data = get_json(_url(
            "works", filter="doi:" + "|".join(chunk), select=WORK_FIELDS,
            **{"per-page": OPENALEX_PER_PAGE},
        ))
        found = {}
        for work in data.get("results", []):
            doi = normalize_doi(work.get("doi"))
            if doi:
                found[doi] = complete_authorships(work)
        for doi in chunk:
            works[doi] = found.get(doi)
        logger.info(
            "openalex works by DOI: chunk %d — %d/%d found",
            start // OPENALEX_CHUNK_SIZE + 1, len(found), len(chunk),
        )
    return works


def fetch_works_by_author(openalex_id: str, year_min: int, year_max: int) -> list[dict[str, Any]]:
    """All OpenAlex works of one author in the year range."""
    works = list(_iter_works(
        f"author.id:{openalex_id},"
        f"publication_year:{year_min}-{year_max},"
        f"type:{OPENALEX_TYPES}"
    ))
    logger.info("openalex works by author %s: %d works", openalex_id, len(works))
    return works


def fetch_authors_details(openalex_ids: list[str]) -> dict[str, dict[str, Any]]:
    """Fetch author profiles (display name, orcid), batched by the OR-filter cap."""
    details: dict[str, dict[str, Any]] = {}
    ids = list(openalex_ids)
    for start in range(0, len(ids), OPENALEX_CHUNK_SIZE):
        chunk = ids[start:start + OPENALEX_CHUNK_SIZE]
        data = get_json(_url(
            "authors", filter="id:" + "|".join(chunk), select="id,display_name,orcid",
            **{"per-page": OPENALEX_PER_PAGE},
        ))
        for author in data.get("results", []):
            details[author["id"]] = author
    return details


def reverse_abstract_index(inverted: dict[str, list[int]] | None) -> str:
    """Reconstruct the abstract text from OpenAlex's inverted index."""
    if not inverted:
        return ""
    words = []
    for word, positions in inverted.items():
        for position in positions:
            words.append((position, word))
    words.sort()
    return " ".join(word for _, word in words)


# ---------------------------------------------------------------------------
# record parsing
# ---------------------------------------------------------------------------

def _bare_orcid(orcid: str | None) -> str | None:
    """https://orcid.org/0000-... -> 0000-..."""
    return orcid.rstrip("/").rsplit("/", 1)[-1] if orcid else None


def _parse_authorship(authorship: dict[str, Any]) -> dict[str, Any]:
    """One authorship -> {openalex_id, name, display_name, orcid, institution_ids, is_epfl}.

    `name` is the name as printed on the work (`raw_author_name`), which is
    what name matching should see; `display_name` is OpenAlex's canonical
    name for the author profile. `openalex_id` is None for authorships that
    OpenAlex did not attach to a profile.
    """
    author = authorship.get("author") or {}
    institution_ids = [
        _short_id(inst["id"]) for inst in authorship.get("institutions") or [] if inst.get("id")
    ]
    return {
        "openalex_id": _short_id(author["id"]) if author.get("id") else None,
        "name": authorship.get("raw_author_name") or author.get("display_name"),
        "display_name": author.get("display_name"),
        "orcid": _bare_orcid(author.get("orcid")),
        "institution_ids": institution_ids,
        "is_epfl": EPFL_OPENALEX_ID in institution_ids,
    }


def parse_work(work: dict[str, Any]) -> dict[str, Any]:
    """Extract the fields used downstream from a raw OpenAlex work.

    Mirrors `infoscience.parse_publication`: normalized DOI, abstract
    rebuilt from the inverted index, authors in authorship order.
    """
    return {
        "openalex_id": _short_id(work["id"]),
        "title": work.get("title"),
        "abstract": reverse_abstract_index(work.get("abstract_inverted_index")) or None,
        "doi": normalize_doi(work.get("doi")),
        "year": work.get("publication_year"),
        "publication_date": work.get("publication_date"),
        "type": work.get("type"),
        "authors": [
            parsed for parsed in map(_parse_authorship, work.get("authorships") or [])
            if parsed["openalex_id"] or parsed["name"]
        ],
    }
