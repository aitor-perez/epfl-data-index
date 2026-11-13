# Infoscience ↔ OpenAlex publication reconciliation

This finds the Infoscience records and the OpenAlex works that describe the same publication, and explains why the rest don't match. It is the "merge publications" step of the pipeline.

## How it works

```bash
python scripts/reconcile_publications.py                  # download (cached) and match, into data/
python scripts/reconcile_publications.py --skip-download  # match the files already downloaded (~10 s)
```

- **Download.** It uses `fetch.infoscience` and `fetch.openalex.fetch_epfl_works`:
  - Infoscience: every EPFL publication dated 2016 or later.
  - OpenAlex: every EPFL-affiliated work dated 2015 or later.

  OpenAlex starts one year earlier because a work Infoscience dates 2016 often has an OpenAlex date in 2015 (online-first, preprint). Neither source has an upper date bound. The records go to `data/infoscience.jsonl` and `data/openalex.jsonl`. The raw API responses are cached in `data/*_cache.jsonl`, about 2.9 GB, so re-runs make no network calls. Set `EDI_PIPELINE_OPENALEX_API_KEY` in `.env`: without it, OpenAlex requests share a small per-IP daily budget.
- **Match.** `merge/publications.py` pairs the records in two steps:
  1. **Same DOI**: confidence 1.
  2. **Same title and agreeing authors**, among the records still unmatched. The confidence is the author score, from 0 to 1. Titles carried by more than 5 records ("Editorial", "Introduction") are skipped.

  DOIs, titles and author names are normalized before comparing (case, accents, HTML and LaTeX markup, punctuation). The result is strictly **one-to-one**. When a record has several candidates, the best one wins, ranked by:
  - same title
  - author score
  - closest year
  - published version rather than preprint

  The output is `data/matches.csv`. Pairs with the same DOI that lose go to `data/duplicates.csv`. Each row of that file says which source holds the duplicate. They are useful in themselves: Infoscience entries to clean up, and OpenAlex records that should have been merged.

## Results

_Figures from a run on 2026-11-13._


**45,837 pairs** (43,673 by DOI, 2,164 by title and authors):

| | Matched |
|---|---|
| Infoscience | 45,837 of 69,788 (65.7%) |
| OpenAlex, 2016 onwards | 45,267 of 68,680 (65.9%) |
| OpenAlex, 2015 | 570 of 5,520 (expected to be low: Infoscience starts in 2016) |

Adding OpenAlex 2015 brought 570 pairs, 535 of them for Infoscience 2016 records. It lifted the 2016 match rate from 50% to 58%, in line with 2017–2018. Going back one more year (2014) would add only about 25 matches.

## Why records are not matched

In short: the unmatched records on both sides are mostly things the other source doesn't contain at all. The matching itself loses very few.

One part of this analysis rests on a sample of 200 DOIs looked up in OpenAlex. Everything else covers all records.

### The matching itself loses little

- No unmatched Infoscience record has a DOI that sits on an unmatched OpenAlex record.
- Only 74 unmatched Infoscience records have an identical title among the unmatched OpenAlex records. Most of those titles are generic ("Postface", "Editorial") and skipped on purpose. In 48 pairs the author lists disagree, for example one author in Infoscience against ten in OpenAlex.

### Why Infoscience records are not matched (23,951 of 69,788)

**1. Types OpenAlex doesn't cover: about 56%.** Infoscience is a repository of everything EPFL produces, not just publications.

| Type | Unmatched | Matched |
|---|---|---|
| Doctoral theses | 4,610 | 1% |
| Conference presentations | 2,742 | 9% |
| Master theses | 1,997 | 0% |
| Conference papers not in proceedings | 1,172 | 32% |
| Patents | 856 | 0% |
| Posters | 712 | 15% |
| Student projects | 561 | 1% |
| Magazine pieces, reports, working papers, books, talks | about 2,000 | under 20% |

Infoscience DOIs starting with 10.5075 are EPFL's own (theses, reports); 5,070 of the unmatched records have one.

**2. Real publications that OpenAlex doesn't tie to EPFL: about 35%.** That's roughly 8,400 articles, conference papers, chapters and preprints. In the 200-DOI sample:

- **69% are in OpenAlex, but none of their authors is affiliated with EPFL.** About 40% of these Infoscience marks as written elsewhere: earlier work by people who joined EPFL later. The rest are EPFL work where OpenAlex lost or never captured the EPFL affiliation.
- **18% are in OpenAlex with no affiliations at all.**
- **10% aren't in OpenAlex**, mostly Zenodo records.
- **2% are in OpenAlex with EPFL** but fell outside the download.

The written-elsewhere flag shows the same thing across all records: only 29% of records written elsewhere are matched, against 68% of those written at EPFL.

### Why OpenAlex records are not matched (23,412 of 68,680 from 2016 on)

**1. Types Infoscience rarely holds: about 37%.** Each row shows how many are unmatched and what share of that type is matched.

- Preprints: 4,499 (24% matched), mostly arXiv (3,250).
- Datasets: 3,030 (4%), mostly Zenodo (2,401).
- Smaller groups: conference abstracts 691, peer reviews 502 (0%), errata 264, paratext 188, software 184.

**2. Another version of a work that is already matched: 1,879.** These have the same title as a matched OpenAlex record: a second article record, a preprint, a dataset.

**3. Associated institutions.** OpenAlex counts some child institutions as part of EPFL, but their output isn't in Infoscience:

| Institution | Unmatched | Matched |
|---|---|---|
| NCCR Chemical Biology | 244 | 1% |
| Swiss Data Science Center | 237 | 14% |
| Swiss Centre for Applied Ecotoxicology | 84 | 0% |

Another 1,186 records show no EPFL-linked author in the stored data, probably because OpenAlex cuts author lists at 100.

**4. About 12,900 articles, conference papers and chapters that Infoscience simply lacks.** This is the real gap. Works with a single EPFL author match only 59% of the time, against 73% for works with two or more. That points to visitors, secondary affiliations and wrong EPFL attributions in OpenAlex. Telling a real Infoscience gap from a wrong OpenAlex attribution would take a manual check of a sample.

### What this means for the headline rates

The "65% matched" on each side understates how well the matching works, because both denominators include records the other source can't hold. Measured on comparable types:

| Source | Type | Matched |
|---|---|---|
| Infoscience | Research articles | 90% |
| Infoscience | Review articles | 89% |
| Infoscience | Conference papers | 73% |
| OpenAlex | Articles | 81% |
| OpenAlex | Reviews | 84% |
