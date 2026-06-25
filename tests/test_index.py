from typing import Literal

import pytest

from epfl_data_index.index import index_documents
from epfl_data_index.models import Document


class SampleDocument(Document):
    type: Literal["sample"] = "sample"


def test_index_documents_rejects_missing_name():
    doc = SampleDocument(id="sample:1", text="some text")
    with pytest.raises(ValueError, match="Document sample:1 is missing required field: name"):
        index_documents([doc])


def test_index_documents_rejects_missing_text():
    doc = SampleDocument(id="sample:1", name="Sample")
    with pytest.raises(ValueError, match="Document sample:1 is missing required field: text"):
        index_documents([doc])
