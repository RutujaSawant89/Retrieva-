"""ORM models.

Every tenant-owned table carries ``organization_id``; those tables are also protected by
PostgreSQL Row-Level Security (see the initial Alembic migration and ``app.db.tenancy``).
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.config import get_settings
from app.db.base import Base, SoftDelete, Timestamps, UUIDPrimaryKey, utcnow

EMBEDDING_DIM = get_settings().embedding_dim

# Tables protected by RLS. Kept here so the migration and tests share one source of truth.
TENANT_TABLES = (
    "documents",
    "document_chunks",
    "document_collections",
    "collection_documents",
    "conversations",
    "messages",
    "message_citations",
    "ingestion_jobs",
    "search_queries",
    "evaluation_datasets",
    "evaluation_runs",
    "evaluation_results",
    "audit_logs",
    "api_usage",
    "research_reports",
)


def _enum(cls: type[enum.Enum], name: str) -> Enum:
    return Enum(cls, name=name, values_callable=lambda e: [m.value for m in e], native_enum=True)


class DocumentStatus(enum.StrEnum):
    UPLOADED = "uploaded"
    QUEUED = "queued"
    EXTRACTING = "extracting"
    CHUNKING = "chunking"
    EMBEDDING = "embedding"
    INDEXING = "indexing"
    COMPLETED = "completed"
    FAILED = "failed"


class Visibility(enum.StrEnum):
    ORGANIZATION = "organization"  # every member of the organization
    PRIVATE = "private"  # owner and organization admins only


class MessageRole(enum.StrEnum):
    USER = "user"
    ASSISTANT = "assistant"


class RunStatus(enum.StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


# --------------------------------------------------------------------------------------
# Identity & tenancy
# --------------------------------------------------------------------------------------


class Organization(UUIDPrimaryKey, Timestamps, SoftDelete, Base):
    __tablename__ = "organizations"

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(String(80), nullable=False, unique=True)

    members: Mapped[list[OrganizationMember]] = relationship(back_populates="organization")


class Role(Base):
    __tablename__ = "roles"

    id: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    name: Mapped[str] = mapped_column(String(32), nullable=False, unique=True)
    description: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    permissions: Mapped[list[str]] = mapped_column(ARRAY(String(64)), nullable=False, default=list)


class User(UUIDPrimaryKey, Timestamps, SoftDelete, Base):
    __tablename__ = "users"
    __table_args__ = (Index("uq_users_email_lower", func.lower(text("email")), unique=True),)

    email: Mapped[str] = mapped_column(String(320), nullable=False)
    full_name: Mapped[str] = mapped_column(String(200), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    memberships: Mapped[list[OrganizationMember]] = relationship(back_populates="user")


class OrganizationMember(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "organization_members"
    __table_args__ = (UniqueConstraint("organization_id", "user_id"),)

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    role_id: Mapped[int] = mapped_column(ForeignKey("roles.id"), nullable=False)

    organization: Mapped[Organization] = relationship(back_populates="members")
    user: Mapped[User] = relationship(back_populates="memberships")
    role: Mapped[Role] = relationship(lazy="joined")


class OrganizationInvitation(UUIDPrimaryKey, Base):
    __tablename__ = "organization_invitations"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    role_id: Mapped[int] = mapped_column(ForeignKey("roles.id"), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    invited_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), default=utcnow
    )

    role: Mapped[Role] = relationship(lazy="joined")
    organization: Mapped[Organization] = relationship()


class RefreshToken(UUIDPrimaryKey, Base):
    """Opaque refresh tokens (stored hashed). Rotation uses ``family_id`` for reuse detection."""

    __tablename__ = "refresh_tokens"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    token_hash: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    family_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    replaced_by_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    user_agent: Mapped[str | None] = mapped_column(String(255))
    ip_address: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), default=utcnow
    )


# --------------------------------------------------------------------------------------
# Documents
# --------------------------------------------------------------------------------------


class Document(UUIDPrimaryKey, Timestamps, SoftDelete, Base):
    __tablename__ = "documents"
    __table_args__ = (
        Index(
            "uq_documents_org_hash_active",
            "organization_id",
            "content_hash",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
        Index("ix_documents_org_status", "organization_id", "status"),
        Index("ix_documents_org_created", "organization_id", "created_at"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    owner_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    original_filename: Mapped[str] = mapped_column(String(500), nullable=False)
    file_type: Mapped[str] = mapped_column(String(16), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(128), nullable=False)
    file_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    storage_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    category: Mapped[str | None] = mapped_column(String(100))
    visibility: Mapped[Visibility] = mapped_column(
        _enum(Visibility, "visibility"), nullable=False, default=Visibility.ORGANIZATION
    )
    page_count: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[DocumentStatus] = mapped_column(
        _enum(DocumentStatus, "document_status"), nullable=False, default=DocumentStatus.UPLOADED
    )
    progress: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
    error_message: Mapped[str | None] = mapped_column(Text)
    chunk_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    embedding_model: Mapped[str | None] = mapped_column(String(200))
    chunking_strategy: Mapped[str | None] = mapped_column(String(32))
    doc_metadata: Mapped[dict] = mapped_column("metadata", JSONB, nullable=False, default=dict)
    indexed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    chunks: Mapped[list[DocumentChunk]] = relationship(
        back_populates="document", cascade="all, delete-orphan", passive_deletes=True
    )


class DocumentChunk(UUIDPrimaryKey, Base):
    __tablename__ = "document_chunks"
    __table_args__ = (
        UniqueConstraint("document_id", "chunk_index"),
        Index("ix_document_chunks_org_model", "organization_id", "embedding_model"),
        Index("ix_document_chunks_content_hash", "organization_id", "content_hash"),
        Index(
            "ix_document_chunks_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_with={"m": 16, "ef_construction": 64},
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    token_count: Mapped[int] = mapped_column(Integer, nullable=False)
    page_number: Mapped[int | None] = mapped_column(Integer)
    page_end: Mapped[int | None] = mapped_column(Integer)
    section: Mapped[str | None] = mapped_column(String(500))
    heading_path: Mapped[list[str]] = mapped_column(ARRAY(String(500)), nullable=False, default=list)
    start_char: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    end_char: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    embedding = mapped_column(Vector(EMBEDDING_DIM), nullable=True)
    embedding_model: Mapped[str | None] = mapped_column(String(200))
    chunk_metadata: Mapped[dict] = mapped_column("metadata", JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), default=utcnow
    )

    document: Mapped[Document] = relationship(back_populates="chunks")


class DocumentCollection(UUIDPrimaryKey, Timestamps, SoftDelete, Base):
    __tablename__ = "document_collections"
    __table_args__ = (
        Index(
            "uq_document_collections_org_name_active",
            "organization_id",
            func.lower(text("name")),
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    visibility: Mapped[Visibility] = mapped_column(
        _enum(Visibility, "visibility"), nullable=False, default=Visibility.ORGANIZATION
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))


class CollectionDocument(Base):
    __tablename__ = "collection_documents"

    collection_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("document_collections.id", ondelete="CASCADE"), primary_key=True
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), primary_key=True, index=True
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    added_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    added_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), default=utcnow
    )


class IngestionJob(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "ingestion_jobs"
    __table_args__ = (Index("ix_ingestion_jobs_org_status", "organization_id", "status"),)

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    task_id: Mapped[str | None] = mapped_column(String(255))
    status: Mapped[DocumentStatus] = mapped_column(
        _enum(DocumentStatus, "document_status"), nullable=False, default=DocumentStatus.QUEUED
    )
    progress: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
    attempts: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
    error_message: Mapped[str | None] = mapped_column(Text)
    # Per-stage durations in milliseconds, e.g. {"extracting": 120, "embedding": 950}.
    stage_timings: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    config: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


# --------------------------------------------------------------------------------------
# Conversations & queries
# --------------------------------------------------------------------------------------


class Conversation(UUIDPrimaryKey, Timestamps, SoftDelete, Base):
    __tablename__ = "conversations"
    __table_args__ = (Index("ix_conversations_org_user_updated", "organization_id", "user_id", "updated_at"),)

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False, default="New conversation")
    # {"document_ids": [...], "collection_ids": [...]} — empty means the whole knowledge base.
    scope: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    summary: Mapped[str | None] = mapped_column(Text)
    summary_message_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    messages: Mapped[list[Message]] = relationship(
        back_populates="conversation", order_by="Message.created_at", passive_deletes=True
    )


class Message(UUIDPrimaryKey, Base):
    __tablename__ = "messages"
    __table_args__ = (Index("ix_messages_conversation_created", "conversation_id", "created_at"),)

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[MessageRole] = mapped_column(_enum(MessageRole, "message_role"), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    # answered | abstained | error (assistant messages only)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="answered")
    retrieval: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    verification: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    llm_provider: Mapped[str | None] = mapped_column(String(64))
    llm_model: Mapped[str | None] = mapped_column(String(200))
    prompt_tokens: Mapped[int | None] = mapped_column(Integer)
    completion_tokens: Mapped[int | None] = mapped_column(Integer)
    retrieval_ms: Mapped[float | None] = mapped_column(Float)
    generation_ms: Mapped[float | None] = mapped_column(Float)
    total_ms: Mapped[float | None] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), default=utcnow
    )

    conversation: Mapped[Conversation] = relationship(back_populates="messages")
    citations: Mapped[list[MessageCitation]] = relationship(
        back_populates="message", order_by="MessageCitation.label_index", passive_deletes=True
    )


class MessageCitation(UUIDPrimaryKey, Base):
    __tablename__ = "message_citations"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    message_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("messages.id", ondelete="CASCADE"), nullable=False, index=True
    )
    label: Mapped[str] = mapped_column(String(16), nullable=False)  # e.g. "S3"
    label_index: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    chunk_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("document_chunks.id", ondelete="SET NULL"), index=True
    )
    document_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("documents.id", ondelete="SET NULL"))
    document_title: Mapped[str] = mapped_column(String(500), nullable=False)
    page_number: Mapped[int | None] = mapped_column(Integer)
    page_end: Mapped[int | None] = mapped_column(Integer)
    section: Mapped[str | None] = mapped_column(String(500))
    passage: Mapped[str] = mapped_column(Text, nullable=False)
    # Offsets into the document's extracted text, for "open at cited passage".
    start_char: Mapped[int | None] = mapped_column(Integer)
    end_char: Mapped[int | None] = mapped_column(Integer)
    retrieval_score: Mapped[float | None] = mapped_column(Float)
    rerank_score: Mapped[float | None] = mapped_column(Float)
    cited_in_answer: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # valid | invalid | uncited
    validation_status: Mapped[str] = mapped_column(String(16), nullable=False)
    support_score: Mapped[float | None] = mapped_column(Float)

    message: Mapped[Message] = relationship(back_populates="citations")


class SearchQuery(UUIDPrimaryKey, Base):
    """One row per retrieval execution (search, chat turn, research subquery, evaluation)."""

    __tablename__ = "search_queries"
    __table_args__ = (Index("ix_search_queries_org_created", "organization_id", "created_at"),)

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    kind: Mapped[str] = mapped_column(String(16), nullable=False)  # search | chat | research | eval
    query: Mapped[str] = mapped_column(Text, nullable=False)
    rewritten_queries: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, default=list)
    strategy: Mapped[str] = mapped_column(String(32), nullable=False)
    config: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    filters: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    result_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    top_score: Mapped[float | None] = mapped_column(Float)
    success: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    timings: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    retrieval_ms: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), default=utcnow
    )


# --------------------------------------------------------------------------------------
# Evaluation
# --------------------------------------------------------------------------------------


class EvaluationDataset(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "evaluation_datasets"
    __table_args__ = (UniqueConstraint("organization_id", "name", "version"),)

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    # [{"question": str, "relevant_passages": [str], "relevant_document_ids": [uuid],
    #   "reference_answer": str | None}]
    items: Mapped[list[dict]] = mapped_column(JSONB, nullable=False, default=list)
    item_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))


class EvaluationRun(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "evaluation_runs"
    __table_args__ = (Index("ix_evaluation_runs_org_created", "organization_id", "created_at"),)

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    dataset_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("evaluation_datasets.id", ondelete="CASCADE"), nullable=False, index=True
    )
    dataset_version: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[RunStatus] = mapped_column(_enum(RunStatus, "run_status"), nullable=False)
    config: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    embedding_model: Mapped[str] = mapped_column(String(200), nullable=False)
    reranker_model: Mapped[str | None] = mapped_column(String(200))
    llm_provider: Mapped[str | None] = mapped_column(String(64))
    llm_model: Mapped[str | None] = mapped_column(String(200))
    metrics: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    error_message: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class EvaluationResult(UUIDPrimaryKey, Base):
    __tablename__ = "evaluation_results"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("evaluation_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    item_index: Mapped[int] = mapped_column(Integer, nullable=False)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    retrieved: Mapped[list[dict]] = mapped_column(JSONB, nullable=False, default=list)
    answer: Mapped[str | None] = mapped_column(Text)
    metrics: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    latency_ms: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)


# --------------------------------------------------------------------------------------
# Audit & usage
# --------------------------------------------------------------------------------------


class AuditLog(UUIDPrimaryKey, Base):
    __tablename__ = "audit_logs"
    __table_args__ = (Index("ix_audit_logs_org_created", "organization_id", "created_at"),)

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    resource_type: Mapped[str | None] = mapped_column(String(64))
    resource_id: Mapped[str | None] = mapped_column(String(64))
    ip_address: Mapped[str | None] = mapped_column(String(64))
    user_agent: Mapped[str | None] = mapped_column(String(255))
    correlation_id: Mapped[str | None] = mapped_column(String(64))
    details: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), default=utcnow
    )


class ApiUsage(UUIDPrimaryKey, Base):
    __tablename__ = "api_usage"
    __table_args__ = (Index("ix_api_usage_org_created", "organization_id", "created_at"),)

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    method: Mapped[str] = mapped_column(String(8), nullable=False)
    route: Mapped[str] = mapped_column(String(255), nullable=False)
    status_code: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    latency_ms: Mapped[float] = mapped_column(Float, nullable=False)
    prompt_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    completion_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    correlation_id: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), default=utcnow
    )


# --------------------------------------------------------------------------------------
# Research
# --------------------------------------------------------------------------------------


class ResearchReport(UUIDPrimaryKey, Timestamps, SoftDelete, Base):
    """A multi-step research run: sub-queries, merged evidence, a cited report and its verification."""

    __tablename__ = "research_reports"
    __table_args__ = (
        Index("ix_research_reports_org_user_created", "organization_id", "user_id", "created_at"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="running")
    scope: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    subqueries: Mapped[list[dict]] = mapped_column(JSONB, nullable=False, default=list)
    report: Mapped[str] = mapped_column(Text, nullable=False, default="")
    evidence: Mapped[list[dict]] = mapped_column(JSONB, nullable=False, default=list)
    conflicts: Mapped[list[dict]] = mapped_column(JSONB, nullable=False, default=list)
    verification: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    llm_provider: Mapped[str | None] = mapped_column(String(64))
    llm_model: Mapped[str | None] = mapped_column(String(200))
    total_ms: Mapped[float | None] = mapped_column(Float)
