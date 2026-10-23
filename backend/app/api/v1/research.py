"""Document comparison, research mode and exports."""

from __future__ import annotations

import uuid
from dataclasses import asdict
from datetime import UTC, datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app.api.deps import CurrentUser, DbSession, client_ip, require
from app.api.v1.chat import _get_conversation, _sse, build_scope
from app.core.errors import NotFoundError, ValidationFailedError
from app.core.permissions import Permission
from app.db.models import DocumentStatus, Message, MessageRole, ResearchReport
from app.schemas.chat import RetrievalOptions, Scope
from app.schemas.common import Message as MessageBody
from app.schemas.common import Page
from app.services import access, audit, comparison, export
from app.services.research import run_research

router = APIRouter(tags=["research"])

Researcher = Annotated[CurrentUser, Depends(require(Permission.RESEARCH))]
Reader = Annotated[CurrentUser, Depends(require(Permission.DOCUMENTS_READ))]
ExportFormat = Literal["md", "docx", "pdf"]


# ---------------------------------------------------------------------------------------------
# Comparison
# ---------------------------------------------------------------------------------------------


class CompareRequest(BaseModel):
    document_a: uuid.UUID
    document_b: uuid.UUID
    summarize: bool = True


@router.post("/compare")
def compare_documents(body: CompareRequest, current: Reader, db: DbSession) -> dict[str, Any]:
    if body.document_a == body.document_b:
        raise ValidationFailedError("Choose two different documents")
    doc_a = access.get_document(db, current, body.document_a)
    doc_b = access.get_document(db, current, body.document_b)
    for doc in (doc_a, doc_b):
        if doc.status != DocumentStatus.COMPLETED:
            raise ValidationFailedError(f"'{doc.title}' has not finished processing")
    return asdict(comparison.compare(db, doc_a, doc_b, summarize=body.summarize))


# ---------------------------------------------------------------------------------------------
# Research
# ---------------------------------------------------------------------------------------------


class ResearchRequest(BaseModel):
    question: str = Field(min_length=5, max_length=2000)
    scope: Scope | None = None
    options: RetrievalOptions = Field(default_factory=RetrievalOptions)


class ResearchSummary(BaseModel):
    id: uuid.UUID
    question: str
    status: str
    created_at: datetime
    total_ms: float | None


@router.post("/research")
def start_research(body: ResearchRequest, current: Researcher, db: DbSession) -> StreamingResponse:
    """Server-Sent Events: meta, plan, subquery*, evidence, token*, verification, done | error."""
    scope = build_scope(db, current, body.scope)
    db.commit()
    return StreamingResponse(
        _sse(
            run_research(
                scope,
                body.question.strip(),
                body.options.to_config(),
                body.scope.model_dump(mode="json") if body.scope else {},
            )
        ),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def _own_report(db: DbSession, current: CurrentUser, report_id: uuid.UUID) -> ResearchReport:
    report = db.scalar(
        select(ResearchReport).where(
            ResearchReport.id == report_id,
            ResearchReport.organization_id == current.org_id,
            ResearchReport.user_id == current.id,
            ResearchReport.deleted_at.is_(None),
        )
    )
    if report is None:
        raise NotFoundError("Research report not found")
    return report


@router.get("/research", response_model=Page[ResearchSummary])
def list_research(
    current: Researcher, db: DbSession, page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100)
) -> Page[ResearchSummary]:
    stmt = select(ResearchReport).where(
        ResearchReport.organization_id == current.org_id,
        ResearchReport.user_id == current.id,
        ResearchReport.deleted_at.is_(None),
    )
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(
        stmt.order_by(ResearchReport.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    )
    items = [
        ResearchSummary(
            id=r.id, question=r.question, status=r.status, created_at=r.created_at, total_ms=r.total_ms
        )
        for r in rows
    ]
    return Page(items=items, total=total, page=page, page_size=page_size)


@router.get("/research/{report_id}")
def get_research(report_id: uuid.UUID, current: Researcher, db: DbSession) -> dict[str, Any]:
    r = _own_report(db, current, report_id)
    return {
        "id": str(r.id),
        "question": r.question,
        "status": r.status,
        "scope": r.scope,
        "subqueries": r.subqueries,
        "report": r.report,
        "evidence": r.evidence,
        "conflicts": r.conflicts,
        "verification": r.verification,
        "llm_provider": r.llm_provider,
        "llm_model": r.llm_model,
        "total_ms": r.total_ms,
        "created_at": r.created_at.isoformat(),
    }


@router.delete("/research/{report_id}", response_model=MessageBody)
def delete_research(
    report_id: uuid.UUID, current: Researcher, request: Request, db: DbSession
) -> MessageBody:
    report = _own_report(db, current, report_id)
    report.deleted_at = datetime.now(UTC)
    report.report = ""
    report.evidence = []
    audit.record(
        db,
        org_id=current.org_id,
        user_id=current.id,
        action="research.deleted",
        resource_type="research",
        resource_id=report.id,
        ip_address=client_ip(request),
    )
    return MessageBody(message="Research report deleted")


def _download(content: bytes, media_type: str, filename: str) -> Response:
    return Response(
        content,
        media_type=media_type,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.get("/research/{report_id}/export")
def export_research(
    report_id: uuid.UUID, current: Researcher, request: Request, db: DbSession, format: ExportFormat = "md"
) -> Response:
    r = _own_report(db, current, report_id)
    if r.status not in ("completed", "abstained"):
        raise ValidationFailedError("Only finished reports can be exported")
    cited = set(r.verification.get("cited_labels", [])) if r.verification else None
    doc = export.ExportDocument(
        title=r.question,
        subtitle=f"Retrieva research report · {r.created_at:%Y-%m-%d %H:%M} UTC · {r.llm_model or 'extractive'}",
        sections=[
            export.ExportSection(None, r.report, export.sources_from_evidence(r.evidence, cited or None))
        ],
    )
    content, media_type, ext = export.render(doc, format)
    audit.record(
        db,
        org_id=current.org_id,
        user_id=current.id,
        action="research.exported",
        resource_type="research",
        resource_id=r.id,
        ip_address=client_ip(request),
        details={"format": format},
    )
    return _download(content, media_type, f"{export.safe_filename(r.question)}.{ext}")


@router.get("/conversations/{conversation_id}/export")
def export_conversation(
    conversation_id: uuid.UUID,
    current: Annotated[CurrentUser, Depends(require(Permission.CHAT))],
    request: Request,
    db: DbSession,
    format: ExportFormat = "md",
) -> Response:
    conversation = _get_conversation(db, current, conversation_id)
    messages = db.scalars(
        select(Message)
        .options(selectinload(Message.citations))
        .where(Message.conversation_id == conversation.id)
        .order_by(Message.created_at)
    ).all()
    sections: list[export.ExportSection] = []
    question = None
    for m in messages:
        if m.role == MessageRole.USER:
            question = m.content
            continue
        cited = [c for c in m.citations if c.cited_in_answer]
        sources = [
            export.ExportSource(
                c.label,
                c.document_title,
                ", ".join(x for x in [f"p. {c.page_number}" if c.page_number else "", c.section or ""] if x),
                c.passage,
            )
            for c in cited
        ]
        body = m.content if m.status == "answered" else f"_{m.content}_"
        sections.append(export.ExportSection(question or "Answer", body, sources))
    doc = export.ExportDocument(
        title=conversation.title,
        subtitle=f"Retrieva conversation · exported {datetime.now(UTC):%Y-%m-%d %H:%M} UTC",
        sections=sections,
    )
    content, media_type, ext = export.render(doc, format)
    audit.record(
        db,
        org_id=current.org_id,
        user_id=current.id,
        action="conversation.exported",
        resource_type="conversation",
        resource_id=conversation.id,
        ip_address=client_ip(request),
        details={"format": format},
    )
    return _download(content, media_type, f"{export.safe_filename(conversation.title)}.{ext}")
