"""Download the pipeline's window year by year, caching the closed years.

The window is made of whole calendar years (see `fetch.window_start`), so
every year but the current one is closed and can be kept on disk:

- the current year is fetched fresh on every run and never cached;
- a past year is read from its cache file, one gzipped JSONL of raw records
  per source and year (`<cache_dir>/<source>/<year>.jsonl.gz`);
- past years are not frozen at the source (retrospective deposits, authors
  linked to a profile later, OpenAlex reprocessing), so a cache file older
  than `max_age_days` is downloaded again, and `refresh=True` forces it for
  every year.

A cache file is written to a temporary name and renamed only once its year
has been downloaded completely: an interrupted run never leaves a partial
year behind, and resumes from the years already done.

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

    `years` defaults to the pipeline's window. `max_age_days=None` keeps
    cached years forever; `refresh=True` downloads every year again. Years
    after the current one are skipped.
    """
    today = today or date.today()
    directory = Path(cache_dir or CACHE_DIR) / source
    for year in (window_years(today=today) if years is None else years):
        if year > today.year:
            continue
        if year == today.year:
            logger.info("%s %d: current year, fetching up to %s", source, year, today.isoformat())
            yield from fetch_range(f"{year}-01-01", today.isoformat())
            continue
        path = directory / f"{year}.jsonl.gz"
        age = _cache_age_days(path)
        fresh = age is not None and (max_age_days is None or age <= max_age_days)
        if fresh and not refresh:
            logger.info("%s %d: from cache (%.0f days old)", source, year, age)
            yield from _read(path)
        else:
            reason = "refresh requested" if refresh and age is not None else (
                "not cached yet" if age is None else f"cache is {age:.0f} days old")
            logger.info("%s %d: fetching (%s)", source, year, reason)
            yield from _fetch_and_store(fetch_range(f"{year}-01-01", f"{year}-12-31"), path)


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
