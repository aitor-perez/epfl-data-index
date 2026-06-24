from __future__ import annotations

from typing import Literal, Optional

from epfl_data_index.models.document import Document, NestedDocument


class Publication(Document):
    type: Literal["publication"] = "publication"
    publication_id: Optional[str] = None
    title: Optional[str] = None
    year: Optional[int] = None
    doi: Optional[str] = None
    infoscience_url: Optional[str] = None
    openalex_url: Optional[str] = None
    abstract: Optional[str] = None

    authors: list["NestedProfessor"] = []
    units: list["NestedUnit"] = []


class NestedPublication(NestedDocument):
    type: Literal["publication"] = "publication"
    publication_id: Optional[str] = None
    title: Optional[str] = None
    year: Optional[int] = None
    doi: Optional[str] = None
