from typing import Literal

from epfl_data_index.models import Document


class SampleDocument(Document):
    type: Literal["sample"] = "sample"
    custom_field: str = ""


def test_document_serialization():
    doc = SampleDocument(
        id="sample:1",
        name="Sample",
        text="Some text",
        custom_field="extra",
    )
    dumped = doc.model_dump()
    assert dumped["id"] == "sample:1"
    assert dumped["type"] == "sample"
    assert dumped["name"] == "Sample"
    assert dumped["text"] == "Some text"
    assert dumped["custom_field"] == "extra"
