"""Reconcile EPFL publications between Infoscience and OpenAlex.

    python scripts/reconcile_publications.py [--since 2016] [--data data] [--refresh]

1. Download (edi_pipeline.pipeline.load_sources), through the yearly cache: each year is
   reused for 30 days, the current one included; --refresh downloads every year again.
   - Infoscience: every EPFL publication dated --since or later (default: the pipeline's
     window, 10 calendar years before the current one)
   - OpenAlex: every EPFL-affiliated work dated one year earlier or later, then the works
     OpenAlex holds for the Infoscience DOIs that this download does not contain
2. Match (edi_pipeline.merge.publications)
   -> <data>/matches.csv, <data>/duplicates.csv

Method and results: src/edi_pipeline/docs/publication-reconciliation.md
"""
import argparse
import logging
from collections import Counter
from pathlib import Path

from edi_pipeline.env import load_env

load_env()  # before the rest of edi_pipeline: its config reads env vars at import time

from edi_pipeline.download import window_years
from edi_pipeline.merge.publications import write_results
from edi_pipeline.pipeline import load_sources, match_publications


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--since", type=int, default=window_years()[0],
                        help="first Infoscience year (OpenAlex starts one year earlier); default: the pipeline's window")
    parser.add_argument("--data", type=Path, default=Path("data"), help="folder for the result files")
    parser.add_argument("--refresh", action="store_true", help="download every year again, ignoring the yearly cache")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    args.data.mkdir(parents=True, exist_ok=True)
    publications, works = load_sources(args.since, args.refresh)
    matches, duplicates = match_publications(publications, works)
    write_results(args.data, matches, duplicates)

    methods = Counter(method for _, _, method, _ in matches)
    print(f"{len(matches)} pairs -> {args.data / 'matches.csv'}  "
          f"({methods['doi']} by DOI, {methods['title+authors']} by title and authors)")
    print(f"{len(duplicates)} same-DOI pairs left out -> {args.data / 'duplicates.csv'}")
    for name, records, side in (("Infoscience", publications, 0), ("OpenAlex", works, 1)):
        found = len({pair[side]["id"] for pair in matches})
        print(f"{name}: {found} of {len(records)} records matched ({found / len(records):.1%})")


if __name__ == "__main__":
    main()
