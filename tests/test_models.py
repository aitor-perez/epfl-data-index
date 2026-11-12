from typing import Literal

from epfl_data_index.models import Document, Professor


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


def test_professor_researcher_fields():
    prof = Professor(
        id="professor:123456",
        name="Jane Doe",
        text="Professor Jane Doe",
        sciper="123456",
        firstname="Jane",
        lastname="Doe",
        is_professor=True,
        orcid="0000-0002-1825-0097",
    )
    dumped = prof.model_dump()
    assert dumped["type"] == "professor"
    assert dumped["is_professor"] is True
    assert dumped["orcid"] == "0000-0002-1825-0097"

    researcher = Professor(
        id="professor:654321",
        name="Postdoc Person",
        text="Researcher Postdoc Person",
        sciper="654321",
        is_professor=False,
    )
    assert researcher.model_dump()["is_professor"] is False
