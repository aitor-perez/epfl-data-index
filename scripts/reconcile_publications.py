"""Reconcile EPFL publications between Infoscience and OpenAlex.

    python scripts/reconcile_publications.py [--data data] [--skip-download]

1. Download (cached: re-runs make no network calls)
   - Infoscience: every EPFL publication dated 2016 or later
   - OpenAlex: every EPFL-affiliated work dated 2015 or later. One year earlier than
     Infoscience, because a work Infoscience dates 2016 often has an OpenAlex date in
     2015 (online-first, preprint). Neither source has an upper date bound.
   -> <data>/infoscience.jsonl, <data>/openalex.jsonl  (raw API responses cached in <data>/*_cache.jsonl)
2. Match (edi_pipeline.merge.publications)
   -> <data>/matches.csv, <data>/duplicates.csv

Method and results: src/edi_pipeline/docs/publication-reconciliation.md
"""
import argparse
import json
import logging
from collections import Counter
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()  # before edi_pipeline: its config reads env vars at import time

from edi_pipeline.cache import JsonlCache
from edi_pipeline.fetch.infoscience import fetch_publications_since, parse_publication
from edi_pipeline.fetch.openalex import fetch_epfl_works
from edi_pipeline.merge.publications import load, match, write_results

INFOSCIENCE_SINCE = "2016"
OPENALEX_SINCE = "2015-01-01"


def download(data: Path) -> None:
    infoscience = [
        parse_publication(item)
        for item in fetch_publications_since(INFOSCIENCE_SINCE, cache=JsonlCache(data / "infoscience_cache.jsonl", "url"))
    ]
    openalex = list(fetch_epfl_works(OPENALEX_SINCE, cache=JsonlCache(data / "openalex_cache.jsonl", "url")))
    for name, records in (("infoscience", infoscience), ("openalex", openalex)):
        path = data / f"{name}.jsonl"
        path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records), encoding="utf-8")
        print(f"{name}: {len(records)} records -> {path}")


def reconcile(data: Path) -> None:
    infoscience = load(data / "infoscience.jsonl", "infoscience")
    openalex = load(data / "openalex.jsonl", "openalex")
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
    parser.add_argument("--data", type=Path, default=Path("data"), help="folder for downloads, caches and results")
    parser.add_argument("--skip-download", action="store_true", help="match the JSONL files already in --data")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    args.data.mkdir(parents=True, exist_ok=True)
    if not args.skip_download:
        download(args.data)
    reconcile(args.data)


if __name__ == "__main__":
    main()
