"""Reconcile EPFL publications between Infoscience and OpenAlex.

    python scripts/reconcile_publications.py [--since 2016] [--data data] [--refresh]

1. Download, through the yearly cache of edi_pipeline.download (each year is reused
   for 30 days, the current one included; --refresh downloads every year again)
   - Infoscience: every EPFL publication dated --since or later (default: the pipeline's
     window, 10 calendar years before the current one)
   - OpenAlex: every EPFL-affiliated work dated one year earlier or later. One year earlier
     than Infoscience, because a work Infoscience dates 2016 often has an OpenAlex date in
     2015 (online-first, preprint). Both sources are capped at today, so records with a
     future date (forthcoming publications) are left out.
   - OpenAlex again, by DOI: the works OpenAlex holds for the Infoscience DOIs that the
     EPFL-affiliated download does not contain. OpenAlex has them without an EPFL
     affiliation, or with no affiliation at all.
   The first two are downloaded side by side, then the DOI lookup runs. Everything goes
   straight to the matcher: no intermediate file.
2. Match (edi_pipeline.merge.publications)
   -> <data>/matches.csv, <data>/duplicates.csv

Method and results: src/edi_pipeline/docs/publication-reconciliation.md
"""
import argparse
import logging
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()  # before edi_pipeline: its config reads env vars at import time

from edi_pipeline.download import (
    download_infoscience,
    download_openalex_by_doi,
    download_openalex_epfl,
    window_years,
)
from edi_pipeline.fetch.infoscience import parse_publication
from edi_pipeline.merge.publications import by_id, infoscience_record, match, openalex_record, write_results


def download(since: int, refresh: bool) -> tuple[dict[str, dict], dict[str, dict]]:
    """Matcher records of both sources, {id: record} each, downloaded side by side."""
    this_year = date.today().year

    def infoscience() -> dict[str, dict]:
        items = download_infoscience(years=range(since, this_year + 1), refresh=refresh)
        return by_id(infoscience_record(parse_publication(item)) for item in items)

    def openalex() -> dict[str, dict]:
        works = download_openalex_epfl(years=range(since - 1, this_year + 1), refresh=refresh)
        return by_id(openalex_record(work) for work in works)

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = pool.submit(infoscience), pool.submit(openalex)
        publications, works = futures[0].result(), futures[1].result()

    # Second OpenAlex pass: Infoscience DOIs that the EPFL-affiliated download does not contain.
    known = {work["doi"] for work in works.values() if work["doi"]}
    missing: dict[int, set[str]] = defaultdict(set)
    for publication in publications.values():
        if publication["doi"] and publication["doi"] not in known and publication["year"]:
            missing[publication["year"]].add(publication["doi"])
    found = by_id(openalex_record(work) for work in download_openalex_by_doi(missing, refresh=refresh))
    added = {key: record for key, record in found.items() if key not in works}
    print(f"OpenAlex by DOI: {sum(map(len, missing.values()))} Infoscience DOIs not in the EPFL download, "
          f"{len(added)} works found")
    return publications, {**works, **added}


def reconcile(data: Path, infoscience: dict[str, dict], openalex: dict[str, dict]) -> None:
    matches, duplicates = match(infoscience, openalex)
    write_results(data, matches, duplicates)

    methods = Counter(method for _, _, method, _ in matches)
    print(f"{len(matches)} pairs -> {data / 'matches.csv'}  "
          f"({methods['doi']} by DOI, {methods['title+authors']} by title and authors)")
    print(f"{len(duplicates)} same-DOI pairs left out -> {data / 'duplicates.csv'}")
    for name, records, side in (("Infoscience", infoscience, 0), ("OpenAlex", openalex, 1)):
        found = len({pair[side]["id"] for pair in matches})
        print(f"{name}: {found} of {len(records)} records matched ({found / len(records):.1%})")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--since", type=int, default=window_years()[0],
                        help="first Infoscience year (OpenAlex starts one year earlier); default: the pipeline's window")
    parser.add_argument("--data", type=Path, default=Path("data"), help="folder for the result files")
    parser.add_argument("--refresh", action="store_true", help="download every year again, ignoring the yearly cache")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    args.data.mkdir(parents=True, exist_ok=True)
    infoscience, openalex = download(args.since, args.refresh)
    reconcile(args.data, infoscience, openalex)


if __name__ == "__main__":
    main()
