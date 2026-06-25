from __future__ import annotations

from typing import Optional
from pydantic import BaseModel


class Document(BaseModel):
    id: str
    type: str
    name: str
    url: Optional[str] = None
    text: str
    created: Optional[str] = None
    updated: Optional[str] = None


class NestedDocument(BaseModel):
    id: str
    type: str
    name: Optional[str] = None
