"""Chat (grounded Q&A), conversations, and search endpoints."""

from __future__ import annotations

import json
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app.api.deps import CurrentUser, DbSession, client_ip, require
from app.core.errors import AppError, NotFoundError, ValidationFailedError
from app.core.permissions import Permission
from app.db.models import Conversation, Message, MessageRole, SearchQuery
from app.schemas.chat import (
    ChatQuery,
    ChatResponse,
    ConversationCreate,
    ConversationDetail,
    ConversationOut,
    ConversationUpdate,
    EvidenceOut,
    MessageOut,
    RegenerateRequest,
    Scope,
    SearchHistoryItem,
    SearchRequest,
    SearchResponse,
)
from app.schemas.common import Message as MessageBody
from app.schemas.common import Page
from app.services import access, audit
from app.services.generation.engine import AnswerRequest, answer_events, evidence_payload
from app.services.retrieval.pipeline import RetrievalPipeline, log_query
from app.services.retrieval.types import RetrievalScope

router = APIRouter(tags=["chat"])

ChatUser = Annotated[CurrentUser, Depends(require(Permission.CHAT))]
SearchUser = Annotated[CurrentUser, Depends(require(Permission.SEARCH))]


def build_scope(db: DbSession, current: CurrentUser, scope: Scope | dict | None) -> RetrievalScope:
    if isinstance(scope, dict):
        scope = Scope.model_validate(scope)
    doc_ids = access.resolve_scope_document_ids(
        db, current, scope.document_ids if scope else None, scope.collection_ids if scope else None
    )
    return RetrievalScope(
        org_id=current.org_id,
        user_id=current.id,
        can_manage=current.can(Permission.DOCUMENTS_MANAGE),
        document_ids=tuple(doc_ids) if doc_ids is not None else None,
    )


def _get_conversation(db: DbSession, current: CurrentUser, conversation_id: uuid.UUID) -> Conversation:
    conversation = db.scalar(
        select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.organization_id == current.org_id,
            Conversation.user_id == current.id,  # conversations are private to their author
            Conversation.deleted_at.is_(None),
        )
    )
    if conversation is None:
        raise NotFoundError("Conversation not found")
    return conversation


def _create_conversation(
    db: DbSession, current: CurrentUser, scope: Scope | None, title: str | None = None
) -> Conversation:
    if scope:
        build_scope(db, current, scope)  # validates access to every referenced document/collection
    conversation = Conversation(
        organization_id=current.org_id,
        user_id=current.id,
        title=(title or "New conversation").strip() or "New conversation",
        scope=scope.model_dump(mode="json") if scope else {},
    )
    db.add(conversation)
    db.flush()
    return conversation


def _prepare(db: DbSession, current: CurrentUser, body: ChatQuery) -> AnswerRequest:
    if body.conversation_id:
        conversation = _get_conversation(db, current, body.conversation_id)
    else:
        conversation = _create_conversation(db, current, body.scope)
    scope = build_scope(db, current, conversation.scope or None)
    db.commit()
    return AnswerRequest(
        scope=scope, question=body.question, conversation_id=conversation.id, config=body.options.to_config()
    )


def _sse(events: Iterator[tuple[str, dict]]) -> Iterator[str]:
    try:
        for name, data in events:
            yield f"event: {name}\ndata: {json.dumps(data, default=str)}\n\n"
    except Exception:  # never leak a traceback into the stream
        yield 'event: error\ndata: {"code": "internal_error", "message": "An unexpected error occurred"}\n\n'


def _stream(req: AnswerRequest) -> StreamingResponse:
    return StreamingResponse(
        _sse(answer_events(req)),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def _load_message(db: DbSession, message_id: uuid.UUID) -> MessageOut:
    db.expire_all()
    message = db.scalar(
        select(Message).options(selectinload(Message.citations)).where(Message.id == message_id)
    )
    if message is None:
        raise NotFoundError("Message not found")
    return MessageOut.model_validate(message)


def _collect(db: DbSession, req: AnswerRequest) -> ChatResponse:
    message_id = None
    for name, data in answer_events(req):
        if name == "error":
            raise AppError(data.get("message", "Request failed"), code=data.get("code", "error"))
        if name == "done":
            message_id = uuid.UUID(data["message_id"])
    if message_id is None:
        raise AppError("No answer was produced", code="internal_error")
    return ChatResponse(conversation_id=req.conversation_id, message=_load_message(db, message_id))


@router.post("/chat/query", response_model=ChatResponse)
def chat_query(body: ChatQuery, current: ChatUser, db: DbSession) -> ChatResponse:
    return _collect(db, _prepare(db, current, body))


@router.post("/chat/stream")
def chat_stream(body: ChatQuery, current: ChatUser, db: DbSession) -> StreamingResponse:
    """Server-Sent Events: ``meta``, ``retrieval``, ``token``…, ``verification``, ``done`` | ``error``."""
    return _stream(_prepare(db, current, body))


@router.post("/chat/messages/{message_id}/regenerate")
def regenerate(
    message_id: uuid.UUID, body: RegenerateRequest, current: ChatUser, db: DbSession
) -> StreamingResponse:
    message = db.scalar(
        select(Message).where(Message.id == message_id, Message.role == MessageRole.ASSISTANT)
    )
    if message is None:
        raise NotFoundError("Message not found")
    conversation = _get_conversation(db, current, message.conversation_id)
    question = db.scalar(
        select(Message.content)
        .where(
            Message.conversation_id == conversation.id,
            Message.role == MessageRole.USER,
            Message.created_at <= message.created_at,
        )
        .order_by(Message.created_at.desc())
        .limit(1)
    )
    if not question:
        raise ValidationFailedError("No question found to regenerate")
    scope = build_scope(db, current, conversation.scope or None)
    db.commit()
    return _stream(
        AnswerRequest(
            scope=scope,
            question=question,
            conversation_id=conversation.id,
            config=body.options.to_config(),
            regenerate_of=message.id,
        )
    )


# ---------------------------------------------------------------------------------------------
# Conversations
# ---------------------------------------------------------------------------------------------


@router.get("/conversations", response_model=Page[ConversationOut])
def list_conversations(
    current: ChatUser,
    db: DbSession,
    page: int = Query(1, ge=1),
    page_size: int = Query(30, ge=1, le=100),
    q: str | None = Query(None, max_length=200),
) -> Page[ConversationOut]:
    counts = (
        select(Message.conversation_id, func.count().label("n")).group_by(Message.conversation_id).subquery()
    )
    stmt = (
        select(Conversation, func.coalesce(counts.c.n, 0))
        .outerjoin(counts, counts.c.conversation_id == Conversation.id)
        .where(
            Conversation.organization_id == current.org_id,
            Conversation.user_id == current.id,
            Conversation.deleted_at.is_(None),
        )
    )
    if q:
        stmt = stmt.where(func.lower(Conversation.title).like(f"%{q.lower()}%"))
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.execute(
        stmt.order_by(Conversation.updated_at.desc()).offset((page - 1) * page_size).limit(page_size)
    ).all()
    items = []
    for conversation, count in rows:
        out = ConversationOut.model_validate(conversation)
        out.message_count = count
        items.append(out)
    return Page(items=items, total=total, page=page, page_size=page_size)


@router.post("/conversations", response_model=ConversationOut, status_code=status.HTTP_201_CREATED)
def create_conversation(body: ConversationCreate, current: ChatUser, db: DbSession) -> ConversationOut:
    return ConversationOut.model_validate(_create_conversation(db, current, body.scope, body.title))


@router.get("/conversations/{conversation_id}", response_model=ConversationDetail)
def get_conversation(conversation_id: uuid.UUID, current: ChatUser, db: DbSession) -> ConversationDetail:
    conversation = _get_conversation(db, current, conversation_id)
    messages = db.scalars(
        select(Message)
        .options(selectinload(Message.citations))
        .where(Message.conversation_id == conversation.id)
        .order_by(Message.created_at)
    ).all()
    return ConversationDetail(
        **ConversationOut.model_validate(conversation).model_dump(exclude={"message_count"}),
        message_count=len(messages),
        summary=conversation.summary,
        messages=[MessageOut.model_validate(m) for m in messages],
    )


@router.patch("/conversations/{conversation_id}", response_model=ConversationOut)
def rename_conversation(
    conversation_id: uuid.UUID, body: ConversationUpdate, current: ChatUser, db: DbSession
) -> ConversationOut:
    conversation = _get_conversation(db, current, conversation_id)
    conversation.title = body.title.strip()
    db.flush()
    return ConversationOut.model_validate(conversation)


@router.delete("/conversations/{conversation_id}", response_model=MessageBody)
def delete_conversation(
    conversation_id: uuid.UUID, current: ChatUser, request: Request, db: DbSession
) -> MessageBody:
    conversation = _get_conversation(db, current, conversation_id)
    conversation.deleted_at = datetime.now(UTC)
    # Message content is removed with the conversation (data deletion), not just hidden.
    db.query(Message).filter(Message.conversation_id == conversation.id).delete()
    audit.record(
        db,
        org_id=current.org_id,
        user_id=current.id,
        action="conversation.deleted",
        resource_type="conversation",
        resource_id=conversation.id,
        ip_address=client_ip(request),
    )
    return MessageBody(message="Conversation deleted")


# ---------------------------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------------------------


@router.post("/search", response_model=SearchResponse)
def search(body: SearchRequest, current: SearchUser, db: DbSession) -> SearchResponse:
    scope = build_scope(db, current, body.scope)
    result = RetrievalPipeline().run(db, scope, body.query, body.options.to_config())
    for i, item in enumerate(result.evidence, start=1):
        item.label = f"R{i}"
    log_query(db, scope, result, "search", filters=body.scope.model_dump(mode="json") if body.scope else {})
    return SearchResponse(
        query=result.query,
        queries=result.queries,
        decisions=result.decisions,
        timings_ms=result.timings_ms,
        total_ms=result.total_ms,
        candidates_considered=result.candidates_considered,
        reranker=result.reranker,
        embedding_model=result.embedding_model,
        results=[EvidenceOut(**evidence_payload(e)) for e in result.evidence],
    )


@router.get("/search/history", response_model=Page[SearchHistoryItem])
def search_history(
    current: SearchUser,
    db: DbSession,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    kind: str | None = Query(None, pattern="^(search|chat|research|eval)$"),
) -> Page[SearchHistoryItem]:
    stmt = select(SearchQuery).where(
        SearchQuery.organization_id == current.org_id, SearchQuery.user_id == current.id
    )
    if kind:
        stmt = stmt.where(SearchQuery.kind == kind)
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(
        stmt.order_by(SearchQuery.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    ).all()
    return Page(
        items=[SearchHistoryItem.model_validate(r) for r in rows], total=total, page=page, page_size=page_size
    )
