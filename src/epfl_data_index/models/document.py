from __future__ import annotations

from typing import Optional
from pydantic import BaseModel


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
