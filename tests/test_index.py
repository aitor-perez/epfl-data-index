from typing import Literal

import pytest
from pydantic import ValidationError

from epfl_data_index.index import index_documents
from epfl_data_index.models import Document


class SampleDocument(Document):
    type: Literal["sample"] = "sample"


def test_document_requires_name():
    with pytest.raises(ValidationError, match="name"):
        SampleDocument(id="sample:1", text="some text")


def test_document_requires_text():
    with pytest.raises(ValidationError, match="text"):
        SampleDocument(id="sample:1", name="Sample")
