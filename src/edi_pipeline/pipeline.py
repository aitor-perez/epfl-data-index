"""The pipeline's steps, as the scripts chain them (see AGENTS.md, *Planned pipeline*).

1. `load_sources`: Infoscience publications and OpenAlex works of the window.
2. `match_publications`: which records of the two sources are the same work.
3. `resolve_researchers`: which author profiles are the same person, and the
   clusters kept because they hold a sciper.
"""
from __future__ import annotations

import logging
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from typing import Any

from edi_pipeline.download import (
    download_infoscience,
    download_openalex_by_doi,
    download_openalex_epfl,
    window_years,
)
from edi_pipeline.fetch.infoscience import parse_publication
from edi_pipeline.merge import publications as publication_matcher

logger = logging.getLogger(__name__)


def slim_work(work: dict[str, Any]) -> dict[str, Any]:
    """A raw OpenAlex work reduced to what matching and author disambiguation read.

    Ten years of works are held in memory at once: the abstract and the
    institutions of every authorship are left in the cache files.
    """
    return {
        "id": work["id"],
        "doi": work.get("doi"),
        "title": work.get("title"),
        "publication_year": work.get("publication_year"),
        "publication_date": work.get("publication_date"),
        "type": work.get("type"),
        "authorships": [
            {
                "author": {
                    "id": (authorship.get("author") or {}).get("id"),
                    "display_name": (authorship.get("author") or {}).get("display_name"),
                    "orcid": (authorship.get("author") or {}).get("orcid"),
                },
                "raw_author_name": authorship.get("raw_author_name"),
                "raw_orcid": authorship.get("raw_orcid"),
            }
            for authorship in work.get("authorships") or []
        ],
    }


def load_sources(
    since: int | None = None, refresh: bool = False
) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    """Step 1: (Infoscience publications by uuid, OpenAlex works by ID), through the yearly cache.

    - Infoscience: every EPFL publication dated `since` or later (default:
      the window's first year), parsed by `parse_publication`.
    - OpenAlex: every EPFL-affiliated work from one year earlier, because a
      work Infoscience dates 2016 often has an OpenAlex date in 2015
      (online-first, preprint); then the works OpenAlex holds for the
      Infoscience DOIs that this download does not contain. All as
      `slim_work`.

    The first two downloads run side by side.
    """
    this_year = date.today().year
    since = window_years()[0] if since is None else since

    def infoscience() -> dict[str, dict[str, Any]]:
        publications: dict[str, dict[str, Any]] = {}
        for item in download_infoscience(years=range(since, this_year + 1), refresh=refresh):
            publications.setdefault(item["uuid"], parse_publication(item))
        return publications

    def openalex() -> dict[str, dict[str, Any]]:
        works: dict[str, dict[str, Any]] = {}
        for work in download_openalex_epfl(years=range(since - 1, this_year + 1), refresh=refresh):
            works.setdefault(work["id"], slim_work(work))
        return works

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = pool.submit(infoscience), pool.submit(openalex)
        publications, works = futures[0].result(), futures[1].result()

    norm_doi = publication_matcher.norm_doi
    known = {norm_doi(work["doi"]) for work in works.values()} - {None}
    missing: dict[int, set[str]] = defaultdict(set)
    for publication in publications.values():
        doi = norm_doi(publication["doi"])
        if doi and doi not in known and publication["year"]:
            missing[publication["year"]].add(doi)
    added = 0
    for work in download_openalex_by_doi(missing, refresh=refresh):
        if work["id"] not in works:
            works[work["id"]] = slim_work(work)
            added += 1
    logger.info(
        "sources: %d Infoscience publications, %d OpenAlex works (%d found by DOI among %d "
        "Infoscience DOIs not in the EPFL download)",
        len(publications), len(works), added, sum(map(len, missing.values())),
    )
    return publications, works


def match_publications(
    publications: dict[str, dict[str, Any]], works: dict[str, dict[str, Any]]
) -> tuple[list[publication_matcher.Pair], list[publication_matcher.Pair]]:
    """Step 2: (matches, same-DOI pairs left out), from `merge.publications.match`."""
    return publication_matcher.match(
        publication_matcher.by_id(map(publication_matcher.infoscience_record, publications.values())),
        publication_matcher.by_id(map(publication_matcher.openalex_record, works.values())),
    )
