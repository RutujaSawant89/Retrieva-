from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


class CollectionCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=2000)
    visibility: Literal["organization", "private"] = "organization"


class CollectionUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    visibility: Literal["organization", "private"] | None = None


class CollectionOut(ORMModel):
    id: uuid.UUID
    name: str
    description: str
    visibility: Literal["organization", "private"]
    created_by: uuid.UUID | None
    created_at: datetime
    updated_at: datetime
    document_count: int = 0
    can_modify: bool = False


class CollectionDocumentsChange(BaseModel):
    document_ids: list[uuid.UUID] = Field(min_length=1, max_length=200)
