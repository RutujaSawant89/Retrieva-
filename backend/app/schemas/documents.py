from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel

StatusLiteral = Literal[
    "uploaded", "queued", "extracting", "chunking", "embedding", "indexing", "completed", "failed"
]
VisibilityLiteral = Literal["organization", "private"]
StrategyLiteral = Literal["recursive", "token", "semantic", "structure"]


class DocumentOut(ORMModel):
    id: uuid.UUID
    title: str
    original_filename: str
    file_type: str
    mime_type: str
    file_size: int
    content_hash: str
    category: str | None
    visibility: VisibilityLiteral
    page_count: int | None
    status: StatusLiteral
    progress: int
    error_message: str | None
    chunk_count: int
    embedding_model: str | None
    chunking_strategy: str | None
    owner_id: uuid.UUID | None
    owner_name: str | None = None
    created_at: datetime
    updated_at: datetime
    indexed_at: datetime | None
    collection_ids: list[uuid.UUID] = Field(default_factory=list)


class IngestionJobOut(ORMModel):
    id: uuid.UUID
    status: StatusLiteral
    progress: int
    attempts: int
    error_message: str | None
    stage_timings: dict
    config: dict
    started_at: datetime | None
    finished_at: datetime | None
    created_at: datetime


class DocumentDetail(DocumentOut):
    metadata: dict
    latest_job: IngestionJobOut | None = None
    can_modify: bool = False


class DocumentStatusOut(BaseModel):
    id: uuid.UUID
    status: StatusLiteral
    progress: int
    error_message: str | None
    chunk_count: int


class UploadResult(BaseModel):
    filename: str
    outcome: Literal["created", "duplicate", "rejected"]
    document: DocumentOut | None = None
    duplicate_of: uuid.UUID | None = None
    error: str | None = None


class UploadResponse(BaseModel):
    results: list[UploadResult]


class DocumentUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=500)
    category: str | None = Field(default=None, max_length=100)
    visibility: VisibilityLiteral | None = None


class ReprocessRequest(BaseModel):
    strategy: StrategyLiteral | None = None
    chunk_size: int | None = Field(default=None, ge=100, le=8000)
    chunk_overlap: int | None = Field(default=None, ge=0, le=2000)
    max_tokens: int | None = Field(default=None, ge=32, le=2048)


class ChunkOut(ORMModel):
    id: uuid.UUID
    chunk_index: int
    content: str
    token_count: int
    page_number: int | None
    page_end: int | None
    section: str | None
    heading_path: list[str]
    start_char: int
    end_char: int


class ContentBlock(BaseModel):
    text: str
    kind: str
    page: int | None
    level: int
    heading_path: list[str]
    start: int
    end: int


class DocumentContent(BaseModel):
    document_id: uuid.UUID
    page_count: int | None
    blocks: list[ContentBlock]
