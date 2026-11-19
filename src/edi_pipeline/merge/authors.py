"""Author disambiguation with setmatch: which author profiles are the same person.

Builds setmatch's inputs from the pipeline's records, runs `setmatch.resolve`
and keeps the clusters anchored on a sciper (see AGENTS.md, *Planned
pipeline*, steps 3 and 4).

Profiles, one per source:

- Infoscience: `sciper_<sciper>` for an author with a sciper, `uuid_<uuid>`
  for a linked profile without one, `ext_<name>` for an author with no
  profile (a name is then the only identity there is);
- OpenAlex: the author ID (`A...`), or `ext_<name>` for an authorship that
  OpenAlex attached to no author.

Publication matches come from `merge.publications`. Their confidence is not
passed on as a reliability: for title matches it is an author-overlap score,
not a probability that the match is right, and setmatch reads a reliability
below 0.5 as evidence against.

ORCID gives hard `must_link` pairs: a researcher whose ORCID, from EPFL's
ORCID integration, is also the ORCID of an OpenAlex author is that author. A
hard pair is never revised by inference, and OpenAlex assigns part of its
ORCIDs by its own matching, so by default an OpenAlex ORCID only counts when
a publisher supplied it on at least one authorship (`raw_orcid`).
"""
from __future__ import annotations

import logging
import re
from typing import Any, Iterable

import pandas as pd
import setmatch

from edi_pipeline import config

logger = logging.getLogger(__name__)

INFOSCIENCE = "infoscience"
OPENALEX = "openalex"

_ORCID = re.compile(r"\d{4}-\d{4}-\d{4}-\d{3}[\dX]")
PAIR_COLUMNS = ["profile_id_1", "source_1", "profile_id_2", "source_2"]


def _orcid(value: Any) -> str | None:
    """Bare ORCID out of a bare one or a URL; None when there is none."""
    found = _ORCID.search(value) if isinstance(value, str) else None
    return found.group(0) if found else None


def _name_id(name: str) -> str:
    return "ext_" + name.strip().replace(",", "").replace(" ", "_")


def infoscience_profile_id(author: dict[str, Any]) -> str:
    """Profile ID of one author of `fetch.infoscience.parse_publication`."""
    if author.get("sciper"):
        return f"sciper_{author['sciper']}"
    if author.get("authority"):
        return f"uuid_{author['authority']}"
    return _name_id(author.get("name") or "unknown")


def _openalex_author(authorship: dict[str, Any]) -> tuple[str | None, str | None]:
    """(profile ID, name as printed) of one raw OpenAlex authorship; ID None when it is empty."""
    author = authorship.get("author") or {}
    name = authorship.get("raw_author_name") or author.get("display_name")
    if author.get("id"):
        return author["id"].rstrip("/").rsplit("/", 1)[-1], name
    return (_name_id(name), name) if name else (None, None)


def setmatch_frames(
    publications: Iterable[dict[str, Any]],
    works: Iterable[dict[str, Any]],
    matches: Iterable[tuple[str, str]],
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """The three frames `setmatch.resolve` takes: publications, authorships, publication matches.

    `publications` are Infoscience publications from `parse_publication`,
    `works` raw OpenAlex works, `matches` pairs (Infoscience uuid, OpenAlex
    work ID). A match naming a record that is not given is left out.
    """
    pub_rows, auth_rows = [], []
    for publication in publications:
        pub_rows.append((publication["uuid"], INFOSCIENCE, publication.get("doi")))
        for author in publication["authors"]:
            auth_rows.append((publication["uuid"], infoscience_profile_id(author), INFOSCIENCE, author["name"]))
    for work in works:
        pub_rows.append((work["id"], OPENALEX, work.get("doi")))
        for authorship in work.get("authorships") or []:
            profile_id, name = _openalex_author(authorship)
            if profile_id:
                auth_rows.append((work["id"], profile_id, OPENALEX, name))
    publications_frame = pd.DataFrame(pub_rows, columns=["publication_id", "source", "doi"]).drop_duplicates(
        ["publication_id", "source"])
    authorships_frame = pd.DataFrame(auth_rows, columns=["publication_id", "profile_id", "source", "name"])
    known = set(zip(publications_frame["publication_id"], publications_frame["source"]))
    match_rows = [
        (uuid, INFOSCIENCE, work_id, OPENALEX)
        for uuid, work_id in matches
        if (uuid, INFOSCIENCE) in known and (work_id, OPENALEX) in known
    ]
    matches_frame = pd.DataFrame(
        match_rows, columns=["publication_id_1", "source_1", "publication_id_2", "source_2"])
    return publications_frame, authorships_frame, matches_frame


def orcid_must_links(
    works: Iterable[dict[str, Any]],
    orcid_by_sciper: dict[str, str],
    scipers: Iterable[str],
    confirmed_only: bool = True,
) -> pd.DataFrame:
    """`must_link` pairs (sciper profile, OpenAlex author) that share an ORCID.

    `orcid_by_sciper` is `fetch.orcid.fetch_orcid_map()`; `scipers` are the
    researchers present in the Infoscience authorships, the only ones a pair
    can name. With `confirmed_only`, an OpenAlex author's ORCID counts only
    if a publisher supplied it on one of the given works. An ORCID claimed by
    several scipers is ignored.
    """
    present = {str(sciper) for sciper in scipers}
    by_orcid: dict[str, set[str]] = {}
    for sciper, orcid in orcid_by_sciper.items():
        if _orcid(orcid):
            by_orcid.setdefault(_orcid(orcid), set()).add(str(sciper))
    sciper_of = {orcid: next(iter(owners)) for orcid, owners in by_orcid.items() if len(owners) == 1}

    author_orcid: dict[str, str] = {}
    confirmed: set[str] = set()
    for work in works:
        for authorship in work.get("authorships") or []:
            author = authorship.get("author") or {}
            orcid = _orcid(author.get("orcid"))
            if not author.get("id") or not orcid:
                continue
            profile_id, _ = _openalex_author(authorship)
            author_orcid[profile_id] = orcid
            if _orcid(authorship.get("raw_orcid")) == orcid:
                confirmed.add(profile_id)

    rows = [
        (f"sciper_{sciper_of[orcid]}", INFOSCIENCE, profile_id, OPENALEX)
        for profile_id, orcid in sorted(author_orcid.items())
        if orcid in sciper_of and sciper_of[orcid] in present
        and (profile_id in confirmed or not confirmed_only)
    ]
    return pd.DataFrame(rows, columns=PAIR_COLUMNS)


def rcp_judge(cache_path: str | None = None) -> setmatch.OpenAICompatibleJudge | None:
    """The LLM judge on EPFL's RCP service, or None when no endpoint is configured.

    Pass it to `resolve_authors(..., judge=rcp_judge(...))`: with None the
    run is plain, so the judge is asked exactly when `RCP_BASE_URL` is set.
    `cache_path` keeps the answers on disk, so a pair is never asked twice.
    """
    if not config.RCP_BASE_URL:
        return None
    from openai import OpenAI  # imported here: plain runs never need it

    client = OpenAI(
        base_url=config.RCP_BASE_URL, api_key=config.RCP_API_KEY or "EMPTY", timeout=120.0, max_retries=2)
    return setmatch.OpenAICompatibleJudge(
        client, config.JUDGE_MODEL,
        request_options={"reasoning_effort": config.JUDGE_REASONING_EFFORT}, cache_path=cache_path)


def resolve_authors(
    publications: list[dict[str, Any]],
    works: list[dict[str, Any]],
    matches: Iterable[tuple[str, str]],
    orcid_by_sciper: dict[str, str] | None = None,
    confirmed_orcids_only: bool = True,
    **resolve_options: Any,
) -> setmatch.ResolveResult:
    """Run setmatch on the given records; `resolve_options` go to `setmatch.resolve` as they are.

    With `orcid_by_sciper`, shared ORCIDs become `must_link` pairs (see
    `orcid_must_links`). Without a `judge` option it is a plain run, with no
    LLM step.
    """
    publications_frame, authorships_frame, matches_frame = setmatch_frames(publications, works, matches)
    must_link = None
    if orcid_by_sciper:
        scipers = {a["sciper"] for p in publications for a in p["authors"] if a.get("sciper")}
        must_link = orcid_must_links(works, orcid_by_sciper, scipers, confirmed_orcids_only)
    logger.info(
        "setmatch: %d publications, %d authorships, %d profiles, %d publication matches, %d must-link pairs",
        len(publications_frame), len(authorships_frame),
        len(authorships_frame.drop_duplicates(["profile_id", "source"])), len(matches_frame),
        0 if must_link is None else len(must_link),
    )
    return setmatch.resolve(
        publications_frame, authorships_frame,
        publication_matches=matches_frame, must_link=must_link, **resolve_options,
    )


def kept_clusters(partition: pd.DataFrame) -> list[dict[str, list[str]]]:
    """The clusters that hold at least one sciper, each with all its profiles.

    `partition` is `ResolveResult.partition` (one row per profile with its
    `block_id`). Each kept cluster is {"scipers", "infoscience", "openalex"}:
    the scipers it holds (several mean setmatch merged two EPFL people, to
    look at), its other Infoscience profile IDs, and its OpenAlex profile
    IDs. A cluster without a sciper is dropped.
    """
    clusters = []
    for _, block in partition.groupby("block_id", sort=True):
        infoscience = sorted(block.loc[block["source"] == INFOSCIENCE, "profile_id"])
        scipers = [pid.removeprefix("sciper_") for pid in infoscience if pid.startswith("sciper_")]
        if scipers:
            clusters.append({
                "scipers": scipers,
                "infoscience": [pid for pid in infoscience if not pid.startswith("sciper_")],
                "openalex": sorted(block.loc[block["source"] == OPENALEX, "profile_id"]),
            })
    return clusters
