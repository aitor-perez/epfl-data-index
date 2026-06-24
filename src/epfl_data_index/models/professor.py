from __future__ import annotations

from typing import Literal, Optional

from epfl_data_index.models.document import Document, NestedDocument


class Professor(Document):
    type: Literal["professor"] = "professor"
    sciper: str
    email: Optional[str] = None
    lastname: Optional[str] = None
    firstname: Optional[str] = None
    creation_date: Optional[str] = None
    class_acc: Optional[str] = None

    publications: list["NestedPublication"] = []
    units: list["ProfessorUnit"] = []


class NestedProfessor(NestedDocument):
    type: Literal["professor"] = "professor"
    sciper: str
    lastname: Optional[str] = None
    firstname: Optional[str] = None
