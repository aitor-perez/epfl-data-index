"""Reconcile Infoscience and OpenAlex publications: find the records that describe the same work.

Input: the records written by scripts/reconcile_publications.py, one JSON object per line
(Infoscience records as returned by fetch.infoscience.parse_publication, OpenAlex works as
returned by fetch.openalex.fetch_epfl_works).

Two records are matched when
  1. they have the same DOI                                 -> confidence 1
  2. or they have the same title and their authors agree    -> confidence = author score (0-1)

Step 2 only looks at the records step 1 left unmatched. In both steps a record
gets at most one partner: when it has several candidates, the best one wins
(same title, then most authors in common, then closest year, then a published
version rather than a preprint). A DOI shared by several records of one source
is a duplicate there (OpenAlex splitting a preprint from its article, Infoscience
holding two entries, or a dataset carrying its paper's DOI): the pairs that
lose are returned separately, see write_results. DOIs, titles and author names
are normalized first, so that differences of case, accents, markup or
punctuation do not hide a match.
"""
from __future__ import annotations

import csv
import html
import json
import re
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path
from urllib.parse import unquote

MAX_TITLE_USES = 5      # a title carried by more records than this ("Editorial", "Introduction") is never matched on
MIN_AUTHOR_SCORE = 0.4  # step 2: minimum share of surname pieces the two author lists must have in common
LONG_AUTHOR_LIST = 100  # OpenAlex returns at most 100 authors per work

DOI = re.compile(r"10\.\d{4,9}/\S+")
MARKUP = re.compile(r"<[^>]+>|\\[a-zA-Z]+|[${}^_~]")  # HTML and MathML tags, LaTeX commands and symbols
ABSTRACT_NUMBER = re.compile(r"^\s*(?:\d+\s*[.:)]|[A-Z]{1,3}\s*:\s*\d+\s*[.:)]?)\s+")  # leading "606. " or "P: 67 "
LETTERS = str.maketrans({"œ": "oe", "æ": "ae", "ø": "o", "ß": "ss", "ł": "l", "đ": "d", "ð": "d", "þ": "th", "ı": "i"})
IGNORED_WORDS = {"the", "a", "an"} | set(  # articles, and Greek letters spelled out where the other source has "α"
    "alpha beta gamma delta epsilon zeta eta theta iota kappa lambda mu nu xi omicron pi rho sigma tau upsilon phi chi psi omega".split()
)


def norm_doi(raw: str | None) -> str | None:
    """'https://doi.org/10.1038/S41586-020-1234-5.' -> '10.1038/s41586-020-1234-5' (None when there is no DOI)."""
    found = DOI.search(re.sub(r"\s+", "", unquote(raw or "")).lower())
    return found.group(0).rstrip(".,;)") if found else None


def fold(text: str) -> str:
    """Lowercase and remove accents: 'Clémence Corminbœuf' -> 'clemence corminboeuf'."""
    text = unicodedata.normalize("NFKD", text.lower().translate(LETTERS))
    return "".join(char for char in text if not unicodedata.combining(char))


def norm_title(raw: str | None) -> str:
    """Comparison key of a title: only its letters and digits, in order.

    'The Enhancement of Er<sup>3+</sup> Emission &amp; α-Decay' -> 'enhancementofer3emissionanddecay'
    """
    text = MARKUP.sub(" ", html.unescape(raw or "")).replace("&", " and ")
    text = ABSTRACT_NUMBER.sub("", text)
    return "".join(word for word in re.findall(r"[a-z0-9]+", fold(text)) if word not in IGNORED_WORDS)


def surname_pieces(names: list[str]) -> Counter:
    """Count the 3-letter pieces of the authors' surnames; given names are ignored.

    The surname is what precedes the comma ('Li, Wei'), else the last word ('Wei Li').
    ['Li, Wei'] -> {' li': 1, 'li ': 1}
    """
    pieces: Counter = Counter()
    for name in names:
        name = fold(name)
        surname = name.split(",")[0] if "," in name else " ".join(name.split()[-1:])
        for word in re.findall(r"[a-z]+", surname):
            word = f" {word} "
            pieces.update(word[start:start + 3] for start in range(len(word) - 2))
    return pieces


def author_score(names_a: list[str], names_b: list[str]) -> float:
    """Share of surname pieces the two author lists have in common, from 0 to 1."""
    pieces_a, pieces_b = surname_pieces(names_a), surname_pieces(names_b)
    common = (pieces_a & pieces_b).total()
    if not common:
        return 0.0
    if max(len(names_a), len(names_b)) >= LONG_AUTHOR_LIST:  # a list may be cut short: compare to the shorter one
        return common / min(pieces_a.total(), pieces_b.total())
    return common / (pieces_a.total() + pieces_b.total() - common)


def load(path: Path, source: str) -> dict[str, dict]:
    """Read a JSONL file into {id: record}, DOI and title ready to compare. A repeated id is kept once."""
    records: dict[str, dict] = {}
    with open(path, encoding="utf-8") as lines:
        for line in lines:
            raw = json.loads(line)
            if source == "infoscience":
                key, year, kind = raw["uuid"], raw.get("year"), None
                authors = [author["name"] for author in raw.get("authors", [])]
            else:
                key, year, kind = raw["id"], raw.get("publication_year"), raw.get("type")
                authors = [a.get("raw_author_name") or (a.get("author") or {}).get("display_name") or ""
                           for a in raw.get("authorships", [])]
            if key not in records:
                records[key] = {"id": key, "doi": norm_doi(raw.get("doi")), "title": norm_title(raw.get("title")),
                                "raw_title": raw.get("title"), "year": int(year) if year else None, "type": kind,
                                "authors": authors}
    return records


Pair = tuple[dict, dict, str, float]  # (Infoscience record, OpenAlex record, method, confidence)


def rank(pub: dict, work: dict, score: float) -> tuple:
    """How good a candidate pair is, to sort on: same title, author score, closest year, not a preprint."""
    year_gap = abs((pub["year"] or 0) - (work["year"] or 0))
    return pub["title"] == work["title"], score, -year_gap, work["type"] != "preprint"


def pair_up(candidates: list[tuple[tuple, Pair]], matched: set[str]) -> tuple[list[Pair], list[Pair]]:
    """Keep the best candidates first, skipping any whose record is already paired: (kept, dropped)."""
    kept, dropped = [], []
    for _, pair in sorted(candidates, key=lambda candidate: candidate[0], reverse=True):
        pub, work = pair[:2]
        if pub["id"] in matched or work["id"] in matched:
            dropped.append(pair)
        else:
            matched.update((pub["id"], work["id"]))
            kept.append(pair)
    return kept, dropped


def match(infoscience: dict[str, dict], openalex: dict[str, dict]) -> tuple[list[Pair], list[Pair]]:
    """Pair the records of the two sources one-to-one: (matches, same-DOI pairs left out as duplicates)."""
    matched: set[str] = set()

    # Step 1 - same DOI.
    by_doi = defaultdict(list)
    for work in openalex.values():
        if work["doi"]:
            by_doi[work["doi"]].append(work)
    candidates = []
    for pub in infoscience.values():
        for work in by_doi.get(pub["doi"], ()):
            score = author_score(pub["authors"], work["authors"])
            candidates.append((rank(pub, work, score), (pub, work, "doi", 1.0)))
    matches, duplicates = pair_up(candidates, matched)

    # Step 2 - same title and agreeing authors, among the records still unmatched.
    uses = Counter(record["title"] for source in (infoscience, openalex) for record in source.values())
    by_title = defaultdict(list)
    for work in openalex.values():
        if work["id"] not in matched:
            by_title[work["title"]].append(work)
    candidates = []
    for pub in infoscience.values():
        if pub["id"] in matched or not pub["title"] or uses[pub["title"]] > MAX_TITLE_USES:
            continue
        for work in by_title.get(pub["title"], ()):
            score = author_score(pub["authors"], work["authors"])
            if score >= MIN_AUTHOR_SCORE:
                candidates.append((rank(pub, work, score), (pub, work, "title+authors", score)))
    matches += pair_up(candidates, matched)[0]
    return matches, duplicates


COLUMNS = ["infoscience_uuid", "openalex_id", "method", "confidence", "infoscience_doi", "openalex_doi",
           "infoscience_year", "openalex_year", "openalex_type", "infoscience_title", "openalex_title"]


def row(pub: dict, work: dict, method: str, confidence: float) -> list:
    return [pub["id"], work["id"], method, round(confidence, 3), pub["doi"], work["doi"],
            pub["year"], work["year"], work["type"], pub["raw_title"], work["raw_title"]]


def duplicate_row(pair: Pair, partner: dict[str, str]) -> list:
    """A left-out pair, with the record each side was matched to instead and which source holds the duplicate."""
    pub, work = pair[:2]
    pub_partner, work_partner = partner.get(pub["id"], ""), partner.get(work["id"], "")
    duplicated = ("openalex" if pub_partner else "") + (" and " if pub_partner and work_partner else "") + \
                 ("infoscience" if work_partner else "")
    return [duplicated, pub_partner, work_partner] + row(*pair)


def write_results(directory: Path, matches: list[Pair], duplicates: list[Pair]) -> None:
    """Write matches.csv (one row per pair, each record at most once) and duplicates.csv
    (same-DOI pairs left out to keep matches.csv one-to-one) into `directory`."""
    with open(directory / "matches.csv", "w", newline="", encoding="utf-8") as out:
        writer = csv.writer(out)
        writer.writerow(COLUMNS)
        writer.writerows(row(*pair) for pair in matches)

    partner = {a["id"]: b["id"] for pub, work, *_ in matches for a, b in ((pub, work), (work, pub))}
    with open(directory / "duplicates.csv", "w", newline="", encoding="utf-8") as out:
        writer = csv.writer(out)
        writer.writerow(["duplicated_in", "infoscience_matched_to", "openalex_matched_to"] + COLUMNS)
        writer.writerows(duplicate_row(pair, partner) for pair in duplicates)
