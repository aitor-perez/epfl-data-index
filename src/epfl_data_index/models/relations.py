from __future__ import annotations

from typing import Optional

from epfl_data_index.models.professor import NestedProfessor
from epfl_data_index.models.publication import NestedPublication
from epfl_data_index.models.unit import NestedUnit


PublicationAuthor = NestedProfessor

ProfessorPublication = NestedPublication

PublicationUnit = NestedUnit

UnitPublication = NestedPublication


class ProfessorUnit(NestedUnit):
    role: Optional[str] = None


class UnitProfessor(NestedProfessor):
    role: Optional[str] = None
