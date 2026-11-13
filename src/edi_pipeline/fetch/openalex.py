"""OpenAlex works and authors client."""
from __future__ import annotations

import logging
import urllib.parse
from typing import Any, Iterator

from edi_pipeline.cache import JsonlCache, get_json
from edi_pipeline.config import (
    OPENALEX_API_KEY,
    OPENALEX_BASE_URL,
    OPENALEX_CHUNK_SIZE,
    OPENALEX_PER_PAGE,
    OPENALEX_TYPES,
)

logger = logging.getLogger(__name__)

# Fields needed for author matching, abstract backfill, and new records.
WORK_FIELDS = "id,doi,title,publication_year,authorships,abstract_inverted_index"

# EPFL's OpenAlex institution; the `lineage` filter also matches its child institutions.
EPFL_INSTITUTION_ID = "I5124864"


def _params(**extra: Any) -> dict[str, Any]:
    params = {"per-page": OPENALEX_PER_PAGE, **extra}
    if OPENALEX_API_KEY:
        params["api_key"] = OPENALEX_API_KEY
    return params


def _clean_openalex_doi(doi: str | None) -> str | None:
    """OpenAlex DOIs come as https://doi.org/10... — normalize to bare lowercase."""
    if not doi:
        return None
    doi = doi.removeprefix("https://doi.org/").strip().lower()
    return doi or None


def fetch_works_by_dois(
    dois: list[str], cache: JsonlCache | None = None
) -> dict[str, dict[str, Any] | None]:
    """Fetch works for the given DOIs, chunked by the OR-filter cap.

    Returns {doi: work or None} — None means "not on OpenAlex" and is kept
    so repeated runs do not refetch misses.
    """
    works: dict[str, dict[str, Any] | None] = {}
    for start in range(0, len(dois), OPENALEX_CHUNK_SIZE):
        chunk = dois[start:start + OPENALEX_CHUNK_SIZE]
        params = _params(
            filter="|".join(f"doi:{doi}" for doi in chunk),
            select=WORK_FIELDS,
        )
        url = f"{OPENALEX_BASE_URL}/works?{urllib.parse.urlencode(params)}"
        data = get_json(url, cache)
        found = {}
        for work in data.get("results", []):
            doi = _clean_openalex_doi(work.get("doi"))
            if doi:
                found[doi] = work
        for doi in chunk:
            works[doi] = found.get(doi)
        logger.info(
            "openalex works by DOI: chunk %d — %d/%d found",
            start // OPENALEX_CHUNK_SIZE + 1, len(found), len(chunk),
        )
    return works



def fetch_epfl_works(
    since: str, until: str | None = None, cache: JsonlCache | None = None, max_pages: int | None = None
) -> Iterator[dict[str, Any]]:
    """Yield every OpenAlex work with an EPFL affiliation published on/after `since` and, if given,
    on/before `until` (both YYYY-MM-DD). Cursor paging; adds `type` and `publication_date` to WORK_FIELDS."""
    date_filter = f"from_publication_date:{since}" + (f",to_publication_date:{until}" if until else "")
    cursor, page = "*", 0
    while cursor and (max_pages is None or page < max_pages):
        params = _params(
            filter=f"authorships.institutions.lineage:{EPFL_INSTITUTION_ID},{date_filter}",
            select=f"{WORK_FIELDS},type,publication_date",
            cursor=cursor,
        )
        data = get_json(f"{OPENALEX_BASE_URL}/works?{urllib.parse.urlencode(params)}", cache)
        yield from data.get("results", [])
        cursor = data.get("meta", {}).get("next_cursor")
        page += 1
        logger.info("openalex EPFL works: page %d (total %s)", page, data.get("meta", {}).get("count"))

def fetch_works_by_author(
    openalex_id: str, year_min: int, year_max: int, cache: JsonlCache | None = None
) -> list[dict[str, Any]]:
    """All OpenAlex works of one author in the year range (cursor paging)."""
    works: list[dict[str, Any]] = []
    cursor = "*"
    while cursor:
        params = _params(
            filter=(
                f"author.id:{openalex_id},"
                f"publication_year:{year_min}-{year_max},"
                f"type:{OPENALEX_TYPES}"
            ),
            select=WORK_FIELDS,
            cursor=cursor,
        )
        url = f"{OPENALEX_BASE_URL}/works?{urllib.parse.urlencode(params)}"
        data = get_json(url, cache)
        works.extend(data.get("results", []))
        cursor = data.get("meta", {}).get("next_cursor")
    logger.info("openalex works by author %s: %d works", openalex_id, len(works))
    return works


def fetch_authors_details(
    openalex_ids: list[str], cache: JsonlCache | None = None
) -> dict[str, dict[str, Any]]:
    """Fetch author profiles (display name, orcid), batched by the OR-filter cap."""
    details: dict[str, dict[str, Any]] = {}
    ids = list(openalex_ids)
    for start in range(0, len(ids), OPENALEX_CHUNK_SIZE):
        chunk = ids[start:start + OPENALEX_CHUNK_SIZE]
        params = _params(
            filter="id:" + "|".join(chunk),
            select="id,display_name,orcid",
        )
        url = f"{OPENALEX_BASE_URL}/authors?{urllib.parse.urlencode(params)}"
        data = get_json(url, cache)
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
