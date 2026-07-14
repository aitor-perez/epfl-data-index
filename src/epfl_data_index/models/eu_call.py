from __future__ import annotations

from typing import Literal, Optional

from epfl_data_index.models.document import Document


class EUCall(Document):
    type: Literal["eu_call"] = "eu_call"
    call: Optional[str] = None
    topic_id: Optional[str] = None
    programme: Optional[str] = None
    type_of_action: Optional[str] = None
    type_of_mga: Optional[str] = None
    status: Optional[str] = None
    deadline_model: Optional[str] = None
    planned_opening_date: Optional[str] = None
    deadline_date: Optional[str] = None
    expected_outcome: Optional[str] = None
    scope: Optional[str] = None
    project_type: Optional[str] = None
    refined_title: Optional[str] = None
