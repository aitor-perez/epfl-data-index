from epfl_data_index.models.document import Document, NestedDocument
from epfl_data_index.models.professor import NestedProfessor, Professor
from epfl_data_index.models.publication import NestedPublication, Publication
from epfl_data_index.models.relations import (
    ProfessorPublication,
    ProfessorUnit,
    PublicationAuthor,
    PublicationUnit,
    UnitProfessor,
    UnitPublication,
)
from epfl_data_index.models.unit import NestedUnit, Unit

Professor.model_rebuild()
Publication.model_rebuild()
Unit.model_rebuild()
