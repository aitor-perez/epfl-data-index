"""Find which author profiles are the same person, and keep the EPFL researchers' clusters.

    python scripts/resolve_authors.py [--since 2016] [--data data] [--refresh]
                                      [--no-judge] [--max-authors N] [--workers 8]

Steps 1 to 4 of the pipeline (AGENTS.md, *Planned pipeline*):

1. Download both sources (as scripts/reconcile_publications.py does, same cache).
2. Match the publications of the two sources.
3. Disambiguate the authors with setmatch, on the Infoscience publications and the OpenAlex
   works matched to them. ORCIDs shared by a sciper and an OpenAlex author are hard links.
   The LLM judge is asked when RCP is configured (RCP_BASE_URL), unless --no-judge; its
   answers are kept in <data>/verdicts.jsonl, one line per question, which can be corrected
   by hand.
4. Keep the clusters that hold a sciper.

Output, in <data>/authors/:
- clusters.jsonl: one kept cluster per line, {"scipers", "infoscience", "openalex"}: its
  scipers (more than one means two EPFL people were merged, to look at), its other
  Infoscience profile IDs and its OpenAlex author IDs
- setmatch's own frames as CSV: partition, pair_probabilities, block_probabilities,
  verdicts, review_pairs, review_publications, review_unlinked_authors
"""
import argparse
import json
import logging
import time
from collections import Counter
from pathlib import Path

from edi_pipeline.env import load_env

load_env()  # before the rest of edi_pipeline: its config reads env vars at import time

from edi_pipeline.download import window_years
from edi_pipeline.fetch.orcid import fetch_orcid_map
from edi_pipeline.merge import authors
from edi_pipeline.pipeline import load_sources, match_publications


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--since", type=int, default=window_years()[0],
                        help="first Infoscience year (OpenAlex starts one year earlier); default: the pipeline's window")
    parser.add_argument("--data", type=Path, default=Path("data"), help="folder for the cache of verdicts and the results")
    parser.add_argument("--refresh", action="store_true", help="download every year again, ignoring the yearly cache")
    parser.add_argument("--no-judge", action="store_true", help="plain run: the LLM judge is not asked")
    parser.add_argument("--max-authors", type=int, default=None,
                        help="leave out publications with this many authors or more (large collaborations)")
    parser.add_argument("--workers", type=int, default=8, help="processes used by setmatch (default 8)")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)   # one line per judge request otherwise
    logging.getLogger("setmatch.model.partition").setLevel(logging.WARNING)  # one line per name
    out_dir = args.data / "authors"
    out_dir.mkdir(parents=True, exist_ok=True)

    publications, works = load_sources(args.since, args.refresh)
    matches, _ = match_publications(publications, works)
    pairs = [(publication["id"], work["id"]) for publication, work, *_ in matches]

    if args.max_authors:
        publications = {k: p for k, p in publications.items() if len(p["authors"]) < args.max_authors}
        works = {k: w for k, w in works.items() if len(w["authorships"]) < args.max_authors}
    pairs = [(uuid, work_id) for uuid, work_id in pairs if uuid in publications and work_id in works]
    matched_works = [works[work_id] for _, work_id in pairs]
    print(f"{len(publications)} Infoscience publications, {len(matched_works)} matched OpenAlex works")

    judge = None if args.no_judge else authors.rcp_judge(str(args.data / "verdicts.jsonl"))
    print("judge:", f"{judge.model}, answers in {args.data / 'verdicts.jsonl'}" if judge else "none (plain run)")

    started = time.time()
    result = authors.resolve_authors(
        list(publications.values()), matched_works, pairs,
        orcid_by_sciper=fetch_orcid_map(), judge=judge, workers=args.workers, seed=42,
    )
    clusters = authors.kept_clusters(result.partition)

    result.to_csv(out_dir)
    with open(out_dir / "clusters.jsonl", "w", encoding="utf-8") as out:
        for cluster in clusters:
            out.write(json.dumps(cluster, ensure_ascii=False) + "\n")

    profiles_per_cluster = Counter(min(len(cluster["openalex"]), 3) for cluster in clusters)
    print(f"setmatch: {time.time() - started:.0f} s, {len(result.partition)} profiles, "
          f"{len(result.verdicts)} verdicts")
    print(f"{len(clusters)} kept clusters -> {out_dir / 'clusters.jsonl'}")
    print(f"  OpenAlex profiles per cluster: none {profiles_per_cluster[0]}, one {profiles_per_cluster[1]}, "
          f"two {profiles_per_cluster[2]}, three or more {profiles_per_cluster[3]}")
    print(f"  clusters with two or more scipers: {sum(len(cluster['scipers']) > 1 for cluster in clusters)}")
    print(f"  pairs to review: {len(result.review_pairs)} -> {out_dir / 'review_pairs.csv'}")


if __name__ == "__main__":
    main()
