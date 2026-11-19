"""Download the pipeline's window year by year, through a cache of one file per year.

The window is made of whole calendar years (see `fetch.window_start`). Each
year of each source is kept on disk as one gzipped JSONL of raw records
(`<cache_dir>/<source>/<year>.jsonl.gz`):

- every year, the current one included, is read from its file for
  `max_age_days` (30 by default) and then downloaded again. The current year
  is downloaded up to the day of the run, so between two downloads it misses
  the records that appeared since;
- past years are not frozen at the source (retrospective deposits, authors
  linked to a profile later, OpenAlex reprocessing), so a cache file older
  than `max_age_days` is downloaded again, and `refresh=True` forces it for
  every year.

A cache file is written to a temporary name and renamed only once its year
has been downloaded completely: an interrupted run never leaves a partial
year behind, and resumes from the years already done.

Three sources are downloaded this way: Infoscience publications, OpenAlex
works affiliated with EPFL, and OpenAlex works looked up by the DOIs of the
Infoscience records that the EPFL-affiliated download does not contain.

Not cached: `fetch.openalex.fetch_works_by_authors`, whose result depends on
the set of authors of each run rather than on a year.
"""
from __future__ import annotations

import gzip
import json
import logging
import os
import time
from datetime import date
from pathlib import Path
from typing import Any, Callable, Iterable, Iterator

from edi_pipeline.config import CACHE_DIR, CACHE_MAX_AGE_DAYS
from edi_pipeline.fetch import infoscience, openalex

logger = logging.getLogger(__name__)

# (since, until) -> raw records of that date range
FetchRange = Callable[[str, str], Iterable[dict[str, Any]]]


def window_years(years: int = 10, today: date | None = None) -> list[int]:
    """Calendar years of the window, oldest first: 2016..2026 during 2026."""
    today = today or date.today()
    return list(range(today.year - years, today.year + 1))


def _cache_age_days(path: Path) -> float | None:
    """Age of a cache file in days, or None when it does not exist."""
    return (time.time() - path.stat().st_mtime) / 86400 if path.exists() else None


def _read(path: Path) -> Iterator[dict[str, Any]]:
    with gzip.open(path, "rt", encoding="utf-8") as lines:
        for line in lines:
            yield json.loads(line)


def _fetch_and_store(records: Iterable[dict[str, Any]], path: Path) -> Iterator[dict[str, Any]]:
    """Yield `records` while writing them to `path`, which appears only if all of them were read."""
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_name(path.name + ".partial")
    complete = False
    try:
        with gzip.open(partial, "wt", encoding="utf-8") as out:
            for record in records:
                out.write(json.dumps(record, ensure_ascii=False) + "\n")
                yield record
        complete = True
    finally:
        if complete:
            os.replace(partial, path)
        else:  # download failed, or the caller stopped reading early
            partial.unlink(missing_ok=True)


def download_years(
    source: str,
    fetch_range: FetchRange,
    years: Iterable[int] | None = None,
    cache_dir: Path | str | None = None,
    max_age_days: float | None = CACHE_MAX_AGE_DAYS,
    refresh: bool = False,
    today: date | None = None,
) -> Iterator[dict[str, Any]]:
    """Yield the raw records of `source` for each year, from cache where allowed.

    `years` defaults to the pipeline's window. A year is read from its cache
    file while that file is younger than `max_age_days` (`None` keeps it
    forever); `refresh=True` downloads every year again. The current year is
    downloaded up to today; years after it are skipped.
    """
    today = today or date.today()
    directory = Path(cache_dir or CACHE_DIR) / source
    for year in (window_years(today=today) if years is None else years):
        if year > today.year:
            continue
        path = directory / f"{year}.jsonl.gz"
        age = _cache_age_days(path)
        fresh = age is not None and (max_age_days is None or age <= max_age_days)
        if fresh and not refresh:
            logger.info("%s %d: from cache (%.0f days old)", source, year, age)
            yield from _read(path)
            continue
        reason = "not cached yet" if age is None else (
            "refresh requested" if refresh else f"cache is {age:.0f} days old")
        until = min(date(year, 12, 31), today).isoformat()
        logger.info("%s %d: fetching up to %s (%s)", source, year, until, reason)
        yield from _fetch_and_store(fetch_range(f"{year}-01-01", until), path)


def download_infoscience(**options: Any) -> Iterator[dict[str, Any]]:
    """Raw EPFL Infoscience publications of the window (see `download_years` for options).

    Parse them with `fetch.infoscience.parse_publication`.
    """
    return download_years(
        "infoscience",
        lambda since, until: infoscience.fetch_publications_since(since, until=until),
        **options,
    )


def download_openalex_epfl(**options: Any) -> Iterator[dict[str, Any]]:
    """Raw EPFL-affiliated OpenAlex works of the window (see `download_years` for options).

    Parse them with `fetch.openalex.parse_work`.
    """
    return download_years(
        "openalex_epfl",
        lambda since, until: openalex.fetch_epfl_works(since, until=until),
        **options,
    )


def download_openalex_by_doi(
    dois_by_year: dict[int, Iterable[str]], **options: Any
) -> Iterator[dict[str, Any]]:
    """Raw OpenAlex works looked up by DOI, cached per year like the other downloads.

    The EPFL-affiliated download misses works that OpenAlex holds without an
    EPFL affiliation (or with no affiliation at all), although Infoscience
    lists them as EPFL publications. `dois_by_year` gives, for each
    Infoscience year, the DOIs of that year's records that the EPFL-affiliated
    download does not contain; the works OpenAlex has for them are yielded.

    A cached year can hold a work that OpenAlex has since tagged as EPFL, so
    the same work may also come from `download_openalex_epfl`: callers should
    keep one record per work ID. DOIs unknown to OpenAlex are not recorded.
    See `download_years` for the options; `years` defaults to the keys of
    `dois_by_year`.
    """
    def fetch_range(since: str, until: str) -> Iterator[dict[str, Any]]:
        dois = sorted(set(dois_by_year.get(int(since[:4]), ())))
        return (work for work in openalex.fetch_works_by_dois(dois).values() if work)

    options.setdefault("years", sorted(dois_by_year))
    return download_years("openalex_by_doi", fetch_range, **options)
