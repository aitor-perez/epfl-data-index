from unittest.mock import MagicMock, patch

import pytest

from epfl_data_index.search import _normalize_doc_type, fetch_all, knn, search


def test_normalize_doc_type():
    assert _normalize_doc_type(None) == []
    assert _normalize_doc_type([]) == []
    assert _normalize_doc_type("publication") == ["publication"]
    assert _normalize_doc_type(["publication", "professor"]) == ["publication", "professor"]


def test_knn_query_building():
    mock_client = MagicMock()
    mock_client.get.return_value = {
        "_source": {"embedding": [0.1, 0.2, 0.3]}
    }
    mock_client.search.return_value = {"hits": {"hits": [{"_id": "2", "_score": 0.85, "_source": {"id": "2"}}], "total": {"value": 1, "relation": "eq"}}}

    with patch("epfl_data_index.search.get_client", return_value=mock_client):
        results = knn(id="unit:123", type="publication", size=10)

    mock_client.get.assert_called_once()
    call_args = mock_client.search.call_args
    body = call_args.kwargs["body"]

    assert body["size"] == 10
    assert body["query"]["bool"]["must"]["knn"]["embedding"]["vector"] == [0.1, 0.2, 0.3]
    assert body["query"]["bool"]["must"]["knn"]["embedding"]["k"] == 10

    assert body["query"]["bool"]["must_not"] == {"term": {"_id": "unit:123"}}
    assert {"terms": {"type": ["publication"]}} in body["query"]["bool"]["filter"]
    assert results == [{"id": "2", "_score": 0.85}]


def test_knn_excludes_text_and_embeddings_by_default():
    mock_client = MagicMock()
    mock_client.get.return_value = {"_source": {"embedding": [0.1, 0.2, 0.3]}}
    mock_client.search.return_value = {"hits": {"hits": [{"_id": "2", "_score": 0.5, "_source": {"id": "2"}}], "total": {"value": 1, "relation": "eq"}}}

    with patch("epfl_data_index.search.get_client", return_value=mock_client):
        results = knn(id="unit:123")

    body = mock_client.search.call_args.kwargs["body"]
    assert set(body["_source"]["excludes"]) == {"text", "embedding"}
    assert results == [{"id": "2", "_score": 0.5}]


def test_knn_includes_text_when_requested():
    mock_client = MagicMock()
    mock_client.get.return_value = {"_source": {"embedding": [0.1, 0.2, 0.3]}}
    mock_client.search.return_value = {"hits": {"hits": [], "total": {"value": 0, "relation": "eq"}}}

    with patch("epfl_data_index.search.get_client", return_value=mock_client):
        knn(id="unit:123", include_text=True)

    body = mock_client.search.call_args.kwargs["body"]
    assert body["_source"]["excludes"] == ["embedding"]


def test_knn_includes_embeddings_when_requested():
    mock_client = MagicMock()
    mock_client.get.return_value = {"_source": {"embedding": [0.1, 0.2, 0.3]}}
    mock_client.search.return_value = {"hits": {"hits": [], "total": {"value": 0, "relation": "eq"}}}

    with patch("epfl_data_index.search.get_client", return_value=mock_client):
        knn(id="unit:123", include_embeddings=True)

    body = mock_client.search.call_args.kwargs["body"]
    assert body["_source"]["excludes"] == ["text"]


def test_knn_includes_text_and_embeddings_when_requested():
    mock_client = MagicMock()
    mock_client.get.return_value = {"_source": {"embedding": [0.1, 0.2, 0.3]}}
    mock_client.search.return_value = {"hits": {"hits": [], "total": {"value": 0, "relation": "eq"}}}

    with patch("epfl_data_index.search.get_client", return_value=mock_client):
        knn(id="unit:123", include_text=True, include_embeddings=True)

    body = mock_client.search.call_args.kwargs["body"]
    assert body["_source"]["excludes"] == []


def test_search_query_building():
    mock_client = MagicMock()
    mock_client.search.return_value = {"hits": {"hits": [{"_id": "1", "_score": 0.9, "_source": {"id": "1"}}], "total": {"value": 1, "relation": "eq"}}}

    with patch("epfl_data_index.search.CONFIG", {
        "EDI_OPENSEARCH_EMBEDDING_MODEL_ID": "test-model",
        "EDI_OPENSEARCH_INDEX_NAME": "test",
    }):
        with patch("epfl_data_index.search.get_client", return_value=mock_client):
            results = search(["machine learning", "healthcare"], type="publication", size=5)

    body = mock_client.search.call_args.kwargs["body"]
    assert results == [{"id": "1", "_score": 0.9}]

    assert body["size"] == 5
    assert body["query"]["bool"]["filter"] == [{"terms": {"type": ["publication"]}}]

    neural_clauses = body["query"]["bool"]["should"]
    assert len(neural_clauses) == 2
    assert neural_clauses[0]["neural"]["embedding"]["query_text"] == "machine learning"
    assert neural_clauses[1]["neural"]["embedding"]["query_text"] == "healthcare"
    for clause in neural_clauses:
        assert clause["neural"]["embedding"]["model_id"] == "test-model"
        assert clause["neural"]["embedding"]["k"] == 5


def test_search_excludes_text_and_embeddings_by_default():
    mock_client = MagicMock()
    mock_client.search.return_value = {"hits": {"hits": [], "total": {"value": 0, "relation": "eq"}}}

    with patch("epfl_data_index.search.CONFIG", {
        "EDI_OPENSEARCH_EMBEDDING_MODEL_ID": "test-model",
        "EDI_OPENSEARCH_INDEX_NAME": "test",
    }):
        with patch("epfl_data_index.search.get_client", return_value=mock_client):
            search("machine learning")

    body = mock_client.search.call_args.kwargs["body"]
    assert set(body["_source"]["excludes"]) == {"text", "embedding"}


def test_search_includes_text_when_requested():
    mock_client = MagicMock()
    mock_client.search.return_value = {"hits": {"hits": [], "total": {"value": 0, "relation": "eq"}}}

    with patch("epfl_data_index.search.CONFIG", {
        "EDI_OPENSEARCH_EMBEDDING_MODEL_ID": "test-model",
        "EDI_OPENSEARCH_INDEX_NAME": "test",
    }):
        with patch("epfl_data_index.search.get_client", return_value=mock_client):
            search("machine learning", include_text=True)

    body = mock_client.search.call_args.kwargs["body"]
    assert body["_source"]["excludes"] == ["embedding"]


def test_search_includes_embeddings_when_requested():
    mock_client = MagicMock()
    mock_client.search.return_value = {"hits": {"hits": [], "total": {"value": 0, "relation": "eq"}}}

    with patch("epfl_data_index.search.CONFIG", {
        "EDI_OPENSEARCH_EMBEDDING_MODEL_ID": "test-model",
        "EDI_OPENSEARCH_INDEX_NAME": "test",
    }):
        with patch("epfl_data_index.search.get_client", return_value=mock_client):
            search("machine learning", include_embeddings=True)

    body = mock_client.search.call_args.kwargs["body"]
    assert body["_source"]["excludes"] == ["text"]


def test_fetch_all_excludes_text_and_embeddings_by_default():
    mock_client = MagicMock()
    mock_client.count.return_value = {"count": 1}
    mock_client.search.return_value = {"hits": {"hits": [{"_id": "1", "_source": {"id": "1"}}], "total": {"value": 1, "relation": "eq"}}}

    with patch("epfl_data_index.search.get_client", return_value=mock_client):
        results = fetch_all()

    body = mock_client.search.call_args.kwargs["body"]
    assert set(body["_source"]["excludes"]) == {"text", "embedding"}
    assert results == [{"id": "1"}]


def test_fetch_all_includes_text_and_embeddings_when_requested():
    mock_client = MagicMock()
    mock_client.count.return_value = {"count": 1}
    mock_client.search.return_value = {"hits": {"hits": [{"_id": "1", "_source": {"id": "1", "text": "hi"}}], "total": {"value": 1, "relation": "eq"}}}

    with patch("epfl_data_index.search.get_client", return_value=mock_client):
        results = fetch_all(include_text=True, include_embeddings=True)

    body = mock_client.search.call_args.kwargs["body"]
    assert body["_source"]["excludes"] == []
    assert results == [{"id": "1", "text": "hi"}]


def test_knn_missing_embedding_raises():
    mock_client = MagicMock()
    mock_client.get.return_value = {"_source": {}}

    with patch("epfl_data_index.search.get_client", return_value=mock_client):
        with pytest.raises(ValueError, match="Document unit:123 has no embedding"):
            knn(id="unit:123")
