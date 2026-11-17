"""Offline tests for edi_pipeline fetchers (HTTP is monkeypatched)."""
from datetime import date
from urllib.parse import parse_qs, urlparse

from edi_pipeline.fetch import normalize_doi, since_years_ago
from edi_pipeline.fetch import infoscience, openalex
from edi_pipeline.fetch.infoscience import parse_publication

UUID_A = "0a1b2c3d-1111-2222-3333-444455556666"
UUID_B = "9f8e7d6c-1111-2222-3333-444455556666"


# --- shared helpers ----------------------------------------------------------

def test_normalize_doi():
    assert normalize_doi(" https://doi.org/10.1000/ABC ") == "10.1000/abc"
    assert normalize_doi("doi:10.1/X") == "10.1/x"
    assert normalize_doi("") is None
    assert normalize_doi(None) is None


def test_since_years_ago():
    assert since_years_ago(10, today=date(2026, 11, 17)) == "2016-11-17"
    assert since_years_ago(1, today=date(2028, 2, 29)) == "2027-02-28"


# --- Infoscience -------------------------------------------------------------

def _item(authors):
    return {
        "uuid": "pub-1",
        "metadata": {
            "dc.title": [{"value": "T"}],
            "dc.identifier.doi": [{"value": "https://doi.org/10.1/ABC"}],
            "dc.date.issued": [{"value": "2021-03"}],
            "dc.contributor.author": authors,
            "cris.virtualsource.sciperId": [{"value": UUID_A}, {"value": UUID_B}],
            "cris.virtual.sciperId": [
                {"value": "123456"},
                {"value": "#PLACEHOLDER_PARENT_METADATA_VALUE#"},
            ],
        },
    }


def test_parse_publication_authority_forms():
    pub = parse_publication(_item([
        {"value": "Linked, With Sciper", "authority": UUID_A},
        {"value": "Linked, No Sciper", "authority": UUID_B},
        {"value": "Pending, Link", "authority": "will be referenced::SCIPER-ID::365358"},
        {"value": "External, Author"},
    ]))
    assert pub["doi"] == "10.1/abc"
    assert pub["year"] == 2021
    assert pub["authors"] == [
        {"name": "Linked, With Sciper", "sciper": "123456", "authority": UUID_A},
        {"name": "Linked, No Sciper", "sciper": None, "authority": UUID_B},
        {"name": "Pending, Link", "sciper": "365358", "authority": None},
        {"name": "External, Author", "sciper": None, "authority": None},
    ]


# --- OpenAlex ----------------------------------------------------------------

def _authorship(i, epfl=False):
    return {
        "author": {"id": f"https://openalex.org/A{i}", "display_name": f"Author {i}",
                   "orcid": "https://orcid.org/0000-0000-0000-0001" if i == 0 else None},
        "raw_author_name": f"A. {i}",
        "institutions": [{"id": f"https://openalex.org/{openalex.EPFL_OPENALEX_ID}"}] if epfl else [],
    }


def _work(wid, n_authors, doi=None):
    return {"id": f"https://openalex.org/{wid}", "doi": doi,
            "authorships": [_authorship(i) for i in range(n_authors)]}


def test_truncated_author_list_is_completed(monkeypatch):
    calls = []

    def fake_get_json(url, headers=None):
        calls.append(url)
        path = urlparse(url).path
        if path.endswith("/works/W2"):
            return _work("W2", 250)
        return {"results": [_work("W1", 3), _work("W2", 100)], "meta": {"next_cursor": None}}

    monkeypatch.setattr(openalex, "get_json", fake_get_json)
    works = list(openalex.fetch_epfl_works(since="2016-11-17"))
    assert [len(w["authorships"]) for w in works] == [3, 250]
    # one list page + one single-work request for the truncated work only
    assert len(calls) == 2


def test_fetch_epfl_works_filter(monkeypatch):
    seen = {}

    def fake_get_json(url, headers=None):
        seen.update(parse_qs(urlparse(url).query))
        return {"results": [], "meta": {"next_cursor": None}}

    monkeypatch.setattr(openalex, "get_json", fake_get_json)
    list(openalex.fetch_epfl_works(since="2016-11-17"))
    assert seen["filter"] == [
        f"authorships.institutions.id:{openalex.EPFL_OPENALEX_ID},"
        f"from_publication_date:2016-11-17,to_publication_date:{date.today().isoformat()}"
    ]
    assert seen["cursor"] == ["*"]


def test_infoscience_date_range_capped_at_today(monkeypatch):
    seen = {}

    def fake_get_json(url, headers=None):
        seen.update(parse_qs(urlparse(url).query))
        return {"_embedded": {"searchResult": {"page": {"totalPages": 1}}}}

    monkeypatch.setattr(infoscience, "get_json", fake_get_json)
    list(infoscience.fetch_publications_since("2016-11-17"))
    assert seen["query"] == [f"dc.date.issued:[2016-11-17 TO {date.today().isoformat()}]"]


def test_doi_filter_names_the_field_once(monkeypatch):
    seen = {}

    def fake_get_json(url, headers=None):
        seen.update(parse_qs(urlparse(url).query))
        return {"results": [_work("W1", 1, doi="https://doi.org/10.1/a")]}

    monkeypatch.setattr(openalex, "get_json", fake_get_json)
    works = openalex.fetch_works_by_dois(["10.1/A", "https://doi.org/10.1/b"])
    assert seen["filter"] == ["doi:10.1/a|10.1/b"]
    assert works["10.1/a"]["id"] == "https://openalex.org/W1"
    assert works["10.1/b"] is None


def test_parse_work():
    work = _work("W9", 2, doi="https://doi.org/10.1/X")
    work["authorships"][1] = _authorship(1, epfl=True)
    work["authorships"].append({"author": {}, "raw_author_name": None, "institutions": []})
    work["abstract_inverted_index"] = {"world": [1], "hello": [0]}
    parsed = openalex.parse_work(work)
    assert parsed["openalex_id"] == "W9"
    assert parsed["doi"] == "10.1/x"
    assert parsed["abstract"] == "hello world"
    assert [a["openalex_id"] for a in parsed["authors"]] == ["A0", "A1"]  # empty authorship dropped
    assert parsed["authors"][0]["name"] == "A. 0"
    assert parsed["authors"][0]["orcid"] == "0000-0000-0000-0001"
    assert [a["is_epfl"] for a in parsed["authors"]] == [False, True]
