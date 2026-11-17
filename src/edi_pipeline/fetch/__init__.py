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


def since_years_ago(years: int, today: date | None = None) -> str:
    """ISO date `years` years before `today` (Feb 29 falls back to Feb 28).

    Used as the lower bound for "works at most N years old".
    """
    today = today or date.today()
    try:
        start = today.replace(year=today.year - years)
    except ValueError:  # Feb 29 in a non-leap target year
        start = today.replace(year=today.year - years, day=28)
    return start.isoformat()
