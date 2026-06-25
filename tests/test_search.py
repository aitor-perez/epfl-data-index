from unittest.mock import MagicMock, patch

import pytest

from epfl_data_index.search import _normalize_doc_type, knn


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
    mock_client.search.return_value = {"hits": {"hits": [], "total": {"value": 0, "relation": "eq"}}}

    with patch("epfl_data_index.search.get_client", return_value=mock_client):
        knn(id="unit:123", type="publication", size=10)

    mock_client.get.assert_called_once()
    call_args = mock_client.search.call_args
    body = call_args.kwargs["body"]

    assert body["size"] == 10
    assert body["query"]["bool"]["must"]["knn"]["embedding"]["vector"] == [0.1, 0.2, 0.3]
    assert body["query"]["bool"]["must"]["knn"]["embedding"]["k"] == 10

    assert body["query"]["bool"]["must_not"] == {"term": {"_id": "unit:123"}}
    assert {"terms": {"type": ["publication"]}} in body["query"]["bool"]["filter"]


def test_knn_missing_embedding_raises():
    mock_client = MagicMock()
    mock_client.get.return_value = {"_source": {}}

    with patch("epfl_data_index.search.get_client", return_value=mock_client):
        with pytest.raises(ValueError, match="Document unit:123 has no embedding"):
            knn(id="unit:123")
