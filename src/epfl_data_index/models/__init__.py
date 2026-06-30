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
from epfl_data_index.models.grant import Grant, NestedGrant

def rebuild_models() -> None:
    """Rebuild all model classes to resolve forward references."""
    namespace = {
        "NestedProfessor": NestedProfessor,
        "NestedPublication": NestedPublication,
        "NestedUnit": NestedUnit,
        "ProfessorUnit": ProfessorUnit,
        "UnitProfessor": UnitProfessor,
    }
    Publication.model_rebuild(_types_namespace=namespace)
    Unit.model_rebuild(_types_namespace=namespace)
    Professor.model_rebuild(_types_namespace=namespace)
    Grant.model_rebuild(_types_namespace=namespace)


rebuild_models()
