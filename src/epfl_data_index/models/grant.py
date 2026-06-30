from __future__ import annotations

from typing import Literal, Optional

from epfl_data_index.models.document import Document, NestedDocument


class Grant(Document):
    type: Literal["grant"] = "grant"
    grant_id: Optional[str] = None
    title: Optional[str] = None
    year: Optional[int] = None
    status: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    duration: Optional[float] = None
    pi_name: Optional[str] = None
    pi_sciper: Optional[str] = None
    epfl_contact_name: Optional[str] = None
    epfl_contact_sciper: Optional[str] = None
    funding_source: Optional[str] = None
    funding_program: Optional[str] = None
    funding_country: Optional[str] = None
    amount: Optional[float] = None
    total_funding: Optional[float] = None
    unit_name: Optional[str] = None
    unit_acronym: Optional[str] = None
    faculty: Optional[str] = None
    laboratory: Optional[str] = None
    unit_url: Optional[str] = None
    project_type: Optional[str] = None
    reference: Optional[str] = None
    internal_id: Optional[str] = None


class NestedGrant(NestedDocument):
    type: Literal["grant"] = "grant"
    grant_id: Optional[str] = None
    title: Optional[str] = None
    year: Optional[int] = None
