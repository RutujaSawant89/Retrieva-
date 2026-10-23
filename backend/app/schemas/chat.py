from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from app.schemas.common import ORMModel
from app.services.retrieval.types import RetrievalConfig


class RetrievalOptions(BaseModel):
    """Client-tunable retrieval settings. Server-side limits keep requests bounded."""

    strategy: Literal["dense", "sparse", "hybrid"] = "hybrid"
    top_k: int = Field(8, ge=1, le=30)
    candidate_k: int = Field(40, ge=5, le=200)
    rrf_k: int = Field(60, ge=1, le=1000)
    dense_weight: float = Field(1.0, ge=0, le=5)
    sparse_weight: float = Field(1.0, ge=0, le=5)
    metric: Literal["cosine", "inner_product"] = "cosine"
    rerank: bool = True
    rewrite: bool | Literal["auto"] = "auto"
    multi_query: bool | Literal["auto"] = "auto"
    expansion: bool | Literal["auto"] = "auto"
    metadata_boost: bool = True
    compression: bool = False
    dedupe: bool = True
    relevance_threshold: float | None = Field(None, ge=-50, le=50)

    def to_config(self) -> RetrievalConfig:
        return RetrievalConfig(**self.model_dump())


class Scope(BaseModel):
    document_ids: list[uuid.UUID] = Field(default_factory=list, max_length=200)
    collection_ids: list[uuid.UUID] = Field(default_factory=list, max_length=50)


class ChatQuery(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    conversation_id: uuid.UUID | None = None
    scope: Scope | None = None  # only used when creating a conversation
    options: RetrievalOptions = Field(default_factory=RetrievalOptions)

    @field_validator("question")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("question must not be blank")
        return value.strip()


class RegenerateRequest(BaseModel):
    options: RetrievalOptions = Field(default_factory=RetrievalOptions)


class CitationOut(ORMModel):
    id: uuid.UUID
    label: str
    chunk_id: uuid.UUID | None
    document_id: uuid.UUID | None
    document_title: str
    page_number: int | None
    page_end: int | None
    section: str | None
    passage: str
    start_char: int | None
    end_char: int | None
    retrieval_score: float | None
    rerank_score: float | None
    cited_in_answer: bool
    validation_status: str
    support_score: float | None


class MessageOut(ORMModel):
    id: uuid.UUID
    role: Literal["user", "assistant"]
    content: str
    status: str
    retrieval: dict[str, Any]
    verification: dict[str, Any]
    llm_provider: str | None
    llm_model: str | None
    prompt_tokens: int | None
    completion_tokens: int | None
    retrieval_ms: float | None
    generation_ms: float | None
    total_ms: float | None
    created_at: datetime
    citations: list[CitationOut] = Field(default_factory=list)


class ConversationOut(ORMModel):
    id: uuid.UUID
    title: str
    scope: dict[str, Any]
    created_at: datetime
    updated_at: datetime
    message_count: int = 0


class ConversationDetail(ConversationOut):
    summary: str | None
    messages: list[MessageOut]


class ConversationCreate(BaseModel):
    title: str | None = Field(default=None, max_length=300)
    scope: Scope | None = None


class ConversationUpdate(BaseModel):
    title: str = Field(min_length=1, max_length=300)


class ChatResponse(BaseModel):
    conversation_id: uuid.UUID
    message: MessageOut


class EvidenceOut(BaseModel):
    label: str
    chunk_id: str
    document_id: str
    document_title: str
    file_type: str
    page_number: int | None
    page_end: int | None
    section: str | None
    location: str
    content: str
    compressed: str | None
    start_char: int
    end_char: int
    scores: dict[str, float | None]
    ranks: dict[str, int | None]


class SearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=2000)
    scope: Scope | None = None
    options: RetrievalOptions = Field(default_factory=RetrievalOptions)


class SearchResponse(BaseModel):
    query: str
    queries: list[str]
    decisions: list[str]
    timings_ms: dict[str, float]
    total_ms: float
    candidates_considered: int
    reranker: str | None
    embedding_model: str | None
    results: list[EvidenceOut]


class SearchHistoryItem(ORMModel):
    id: uuid.UUID
    kind: str
    query: str
    rewritten_queries: list[str]
    strategy: str
    result_count: int
    top_score: float | None
    success: bool
    retrieval_ms: float
    created_at: datetime
