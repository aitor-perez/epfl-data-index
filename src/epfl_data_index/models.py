from __future__ import annotations

from typing import Literal, Optional
from pydantic import BaseModel


################################################################
# Base documents (fields shared by every document type)
################################################################


class Document(BaseModel):
    id: str
    type: str
    name: Optional[str] = None
    url: Optional[str] = None
    text: Optional[str] = None
    created: Optional[str] = None
    updated: Optional[str] = None


class NestedDocument(BaseModel):
    id: str
    type: str
    name: Optional[str] = None


################################################################
# Publications
################################################################


class Publication(Document):
    type: Literal["publication"] = "publication"
    publication_id: Optional[str] = None
    title: Optional[str] = None
    year: Optional[int] = None
    doi: Optional[str] = None
    infoscience_url: Optional[str] = None
    openalex_url: Optional[str] = None
    abstract: Optional[str] = None

    authors: list[PublicationAuthor] = []
    units: list[PublicationUnit] = []


class NestedPublication(NestedDocument):
    type: Literal["publication"] = "publication"
    publication_id: Optional[str] = None
    title: Optional[str] = None
    year: Optional[int] = None
    doi: Optional[str] = None


################################################################
# Professors
################################################################


class Professor(Document):
    type: Literal["professor"] = "professor"
    sciper: str
    email: Optional[str] = None
    lastname: Optional[str] = None
    firstname: Optional[str] = None
    creation_date: Optional[str] = None
    class_acc: Optional[str] = None

    publications: list[ProfessorPublication] = []
    units: list[ProfessorUnit] = []


class NestedProfessor(NestedDocument):
    type: Literal["professor"] = "professor"
    sciper: str
    lastname: Optional[str] = None
    firstname: Optional[str] = None


################################################################
# Units
################################################################


class Unit(Document):
    type: Literal["unit"] = "unit"
    cf: str
    unit_name: Optional[str] = None
    unit_type: Optional[str] = None
    cf_level_2: Optional[str] = None
    cf_level_3: Optional[str] = None
    acronym_level_2: Optional[str] = None
    acronym_level_3: Optional[str] = None

    professors: list[UnitProfessor] = []
    publications: list[UnitPublication] = []


class NestedUnit(NestedDocument):
    type: Literal["unit"] = "unit"
    cf: str
    unit_name: Optional[str] = None
    unit_type: Optional[str] = None
    cf_level_2: Optional[str] = None
    cf_level_3: Optional[str] = None
    acronym_level_2: Optional[str] = None
    acronym_level_3: Optional[str] = None


################################################################
# Specific classes for many to many relations
################################################################


PublicationAuthor = NestedProfessor

ProfessorPublication = NestedPublication

PublicationUnit = NestedUnit

UnitPublication = NestedPublication


class ProfessorUnit(NestedUnit):
    role: Optional[str] = None


class UnitProfessor(NestedProfessor):
    role: Optional[str] = None


################################################################
# Rebuild models with relations
################################################################

Professor.model_rebuild()
Publication.model_rebuild()
Unit.model_rebuild()
