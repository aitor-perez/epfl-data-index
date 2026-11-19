"""Offline tests for edi_pipeline fetchers (HTTP is monkeypatched)."""
from datetime import date
from urllib.parse import parse_qs, urlparse

from edi_pipeline.fetch import normalize_doi, window_start
from edi_pipeline import download
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


def test_window_start():
    assert window_start(today=date(2026, 11, 19)) == "2016-01-01"
    assert window_start(today=date(2027, 1, 1)) == "2017-01-01"
    assert window_start(3, today=date(2028, 2, 29)) == "2025-01-01"


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
        f"authorships.institutions.lineage:{openalex.EPFL_OPENALEX_ID},"
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


# --- step 5: works by kept authors ----------------------------------------------------

def test_works_by_authors_batches_and_dedups(monkeypatch):
    filters = []

    def fake_get_json(url, headers=None):
        filters.append(parse_qs(urlparse(url).query)["filter"][0])
        # W1 is shared by an author of each batch
        results = [_work("W1", 1), _work(f"W{len(filters) + 1}", 1)]
        return {"results": results, "meta": {"next_cursor": None}}

    monkeypatch.setattr(openalex, "get_json", fake_get_json)
    ids = [f"https://openalex.org/A{i:03d}" for i in range(150)]
    works = list(openalex.fetch_works_by_authors(ids, since="2016-11-19"))
    assert len(filters) == 2  # 150 authors -> 2 queries, not 150
    assert filters[0].count("|") == 99 and filters[0].startswith("author.id:A000|A001")
    assert filters[0].endswith(f",from_publication_date:2016-11-19,to_publication_date:{date.today().isoformat()}")
    assert sorted(_w["id"].rsplit("/", 1)[-1] for _w in works) == ["W1", "W2", "W3"]


def test_publications_of():
    def pub(uuid, *authors):
        return {"uuid": uuid, "authors": [{"name": "n", "sciper": s, "authority": a} for s, a in authors]}

    pubs = [
        pub("by-uuid", (None, UUID_B)),
        pub("by-pending-sciper", ("365358", None)),
        pub("other", ("999999", UUID_A), (None, None)),
    ]
    kept = infoscience.publications_of(pubs, authorities=[UUID_B], scipers=[365358])
    assert [p["uuid"] for p in kept] == ["by-uuid", "by-pending-sciper"]


# --- yearly download cache ---------------------------------------------------

def _fake_source(calls):
    def fetch_range(since, until):
        calls.append((since, until))
        return [{"id": f"{since[:4]}-{i}"} for i in range(2)]
    return fetch_range


def test_download_years_caches_closed_years_only(tmp_path):
    today = date(2026, 11, 19)
    calls = []
    run = lambda **kw: list(download.download_years(
        "src", _fake_source(calls), years=[2024, 2025, 2026, 2027], cache_dir=tmp_path, today=today, **kw))

    first = run()
    assert calls == [("2024-01-01", "2024-12-31"), ("2025-01-01", "2025-12-31"), ("2026-01-01", "2026-11-19")]
    assert sorted(p.name for p in (tmp_path / "src").iterdir()) == ["2024.jsonl.gz", "2025.jsonl.gz", "2026.jsonl.gz"]

    calls.clear()
    assert run() == first  # same records, every year now read from disk
    assert calls == []

    assert run(max_age_days=0) == first
    assert len(calls) == 3  # nothing is young enough: all three years fetched again

    calls.clear()
    run(refresh=True)
    assert len(calls) == 3


def test_download_years_refetches_stale_cache(tmp_path):
    import os, time
    calls = []
    run = lambda: list(download.download_years(
        "src", _fake_source(calls), years=[2025], cache_dir=tmp_path, max_age_days=30, today=date(2026, 11, 19)))
    run()
    old = time.time() - 31 * 86400
    os.utime(tmp_path / "src" / "2025.jsonl.gz", (old, old))
    run()
    assert len(calls) == 2  # 31 days old -> downloaded again


def test_interrupted_download_leaves_no_cache_file(tmp_path):
    def failing(since, until):
        yield {"id": 1}
        raise RuntimeError("network down")

    try:
        list(download.download_years("src", failing, years=[2025], cache_dir=tmp_path, today=date(2026, 11, 19)))
    except RuntimeError:
        pass
    assert list((tmp_path / "src").iterdir()) == []


def test_window_years():
    assert download.window_years(today=date(2026, 11, 19)) == list(range(2016, 2027))


# --- HTTP retries ------------------------------------------------------------

def test_retry_after_header_is_obeyed(monkeypatch):
    from edi_pipeline import http_client

    class Response:
        def __init__(self, status, headers=None):
            self.status_code, self.headers = status, headers or {}
        def raise_for_status(self): pass
        def json(self): return {"ok": True}

    responses = [Response(429, {"Retry-After": "900"}), Response(429), Response(200)]
    waits = []
    monkeypatch.setattr(http_client.requests, "get", lambda *a, **k: responses.pop(0))
    monkeypatch.setattr(http_client.time, "sleep", waits.append)
    assert http_client.get_json("https://example.org") == {"ok": True}
    # header obeyed (+ margin), then the configured delay for a refusal without header, then the polite pause
    assert waits == [905, http_client.WAIT_ON_RETRY[1], http_client.POLITE_DELAY_SECONDS]


# --- publication matcher inputs ----------------------------------------------

def test_matcher_takes_pipeline_records_directly():
    from edi_pipeline.merge import publications as merge

    pub = parse_publication(_item([{"value": "Li, Wei", "authority": UUID_A}]))
    pub["doi"] = "10.1234/abc"  # the matcher only accepts realistic DOIs (10.<4+ digits>/...)
    same_doi = _work("W1", 1, doi="https://doi.org/10.1234/ABC")
    other = _work("W2", 1, doi="https://doi.org/10.5678/zzz")
    infoscience_records = merge.by_id([merge.infoscience_record(pub)])
    openalex_records = merge.by_id(merge.openalex_record(w) for w in (same_doi, other, same_doi))
    assert list(openalex_records) == ["https://openalex.org/W1", "https://openalex.org/W2"]
    matches, duplicates = merge.match(infoscience_records, openalex_records)
    assert [(p["id"], w["id"], method) for p, w, method, _ in matches] == [("pub-1", "https://openalex.org/W1", "doi")]
    assert duplicates == []


def test_download_openalex_by_doi_caches_per_year(tmp_path, monkeypatch):
    asked = []

    def fake_by_dois(dois):
        asked.append(list(dois))
        return {doi: ({"id": f"W-{doi}"} if "found" in doi else None) for doi in dois}

    monkeypatch.setattr(download.openalex, "fetch_works_by_dois", fake_by_dois)
    missing = {2025: {"10.1234/found-a", "10.1234/unknown"}, 2026: {"10.1234/found-b"}}
    run = lambda: list(download.download_openalex_by_doi(missing, cache_dir=tmp_path, today=date(2026, 11, 19)))
    assert sorted(w["id"] for w in run()) == ["W-10.1234/found-a", "W-10.1234/found-b"]
    assert asked == [["10.1234/found-a", "10.1234/unknown"], ["10.1234/found-b"]]
    asked.clear()
    assert len(run()) == 2
    assert asked == []  # both years from cache


def test_client_errors_are_not_retried(monkeypatch):
    from edi_pipeline import http_client

    class Response:
        status_code, headers, text = 400, {}, "bad filter"

    calls, waits = [], []
    monkeypatch.setattr(http_client.requests, "get", lambda *a, **k: calls.append(1) or Response())
    monkeypatch.setattr(http_client.time, "sleep", waits.append)
    try:
        http_client.get_json("https://example.org")
        assert False, "should have raised"
    except RuntimeError as error:
        assert "HTTP 400" in str(error)
    assert len(calls) == 1 and waits == []


# --- units -------------------------------------------------------------------

def test_unit_members_and_researcher_links(monkeypatch):
    from edi_pipeline.fetch import units

    full = {"code": 10659, "acronym": "LAB-A", "name": "Lab A", "path": [{"acronym": "EPFL"}, {"acronym": "LAB-A"}],
            "head": {"sciper": "100001", "name": "Head", "firstname": "Ann", "email": "x"},
            "people": [{"sciper": "100001", "name": "Head", "firstname": "Ann", "position": "Full Professor", "email": "x"},
                       {"sciper": "100002", "name": "Admin", "firstname": "Bob", "position": "Administrative Assistant"}]}
    faculty = {"code": 10000, "acronym": "FAC", "name": "Faculty", "path": [{"acronym": "EPFL"}, {"acronym": "FAC"}],
               "subunits": [{"acronym": "LAB-A"}]}
    answers = {"acro=LAB-A": full, "acro=FAC": faculty, "acro=GONE": {}}
    monkeypatch.setattr(units, "get_json", lambda url: answers[url.split("?")[1]])
    found = units.fetch_units(["LAB-A", "FAC", "GONE", "LAB-A"])
    assert found["GONE"] is None  # renamed, closed, or not an EPFL unit
    assert found["LAB-A"]["members"] == [
        {"sciper": "100001", "firstname": "Ann", "lastname": "Head", "position": "Full Professor"},
        {"sciper": "100002", "firstname": "Bob", "lastname": "Admin", "position": "Administrative Assistant"},
    ]
    assert found["FAC"]["members"] is None  # a larger unit comes without people
    links = units.units_by_member(found, scipers=[100001, "999999"])
    assert links == {"100001": [{"acronym": "LAB-A", "cf": "10659", "name": "Lab A", "position": "Full Professor"}]}
