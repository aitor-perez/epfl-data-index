from __future__ import annotations

from typing import Literal, Optional

from epfl_data_index.models.document import Document, NestedDocument


class Unit(Document):
    type: Literal["unit"] = "unit"
    cf: str
    unit_name: Optional[str] = None
    unit_type: Optional[str] = None
    cf_level_2: Optional[str] = None
    cf_level_3: Optional[str] = None
    acronym_level_2: Optional[str] = None
    acronym_level_3: Optional[str] = None

    professors: list["UnitProfessor"] = []
    publications: list["NestedPublication"] = []


class NestedUnit(NestedDocument):
    type: Literal["unit"] = "unit"
    cf: str
    unit_name: Optional[str] = None
    unit_type: Optional[str] = None
    cf_level_2: Optional[str] = None
    cf_level_3: Optional[str] = None
    acronym_level_2: Optional[str] = None
    acronym_level_3: Optional[str] = None
