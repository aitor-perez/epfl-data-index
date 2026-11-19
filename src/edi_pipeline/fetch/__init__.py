"""Fetchers for live sources, plus small helpers shared between them."""
from __future__ import annotations

from datetime import date

_DOI_PREFIXES = ("https://doi.org/", "http://doi.org/", "https://dx.doi.org/", "http://dx.doi.org/", "doi:")


def normalize_doi(doi: object) -> str | None:
    """Bare lowercase DOI (resolver prefixes stripped), or None when empty.

    Applied to both sources so DOIs compare as exact strings.
    """
    if doi is None:
        return None
    value = str(doi).strip().lower()
    for prefix in _DOI_PREFIXES:
        if value.startswith(prefix):
            value = value[len(prefix):]
            break
    return value.strip() or None


def window_start(years: int = 10, today: date | None = None) -> str:
    """First day of the calendar year `years` years before the current one.

    The pipeline works on whole calendar years: on 2026-11-19, `window_start(10)`
    is "2016-01-01", so the window is 2016-2026, both included. Unlike a
    sliding "today minus 10 years", the window only moves on 1 January, and
    every year but the current one is closed.
    """
    today = today or date.today()
    return f"{today.year - years}-01-01"
