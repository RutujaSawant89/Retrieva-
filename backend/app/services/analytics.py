"""Analytics computed from the database. Nothing here is estimated or hard-coded.

All queries are restricted to one organization (and additionally by RLS).
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlalchemy import Date, Float, Integer, cast, func, literal, select
from sqlalchemy.orm import Session

from app.db.models import (
    ApiUsage,
    Conversation,
    Document,
    DocumentChunk,
    DocumentStatus,
    IngestionJob,
    Message,
    MessageRole,
    SearchQuery,
)


def _since(days: int) -> datetime:
    return datetime.now(UTC) - timedelta(days=days)


def _day_series(rows: list[tuple[date, Any]], days: int, default: Any = 0) -> list[dict[str, Any]]:
    by_day = {d.isoformat() if isinstance(d, date) else str(d): v for d, v in rows}
    today = datetime.now(UTC).date()
    return [
        {
            "date": (today - timedelta(days=offset)).isoformat(),
            "value": by_day.get((today - timedelta(days=offset)).isoformat(), default),
        }
        for offset in range(days - 1, -1, -1)
    ]


def _round(value: float | None, digits: int = 1) -> float | None:
    return None if value is None else round(float(value), digits)


def overview(db: Session, org_id: uuid.UUID) -> dict[str, Any]:
    active_docs = (Document.organization_id == org_id) & Document.deleted_at.is_(None)
    total_documents = db.scalar(select(func.count()).where(active_docs)) or 0
    indexed = (
        db.scalar(select(func.count()).where(active_docs, Document.status == DocumentStatus.COMPLETED)) or 0
    )
    processing = (
        db.scalar(
            select(func.count()).where(
                active_docs, Document.status.not_in([DocumentStatus.COMPLETED, DocumentStatus.FAILED])
            )
        )
        or 0
    )
    failed_docs = (
        db.scalar(select(func.count()).where(active_docs, Document.status == DocumentStatus.FAILED)) or 0
    )
    total_chunks = db.scalar(select(func.count()).where(DocumentChunk.organization_id == org_id)) or 0
    storage_bytes = db.scalar(select(func.coalesce(func.sum(Document.file_size), 0)).where(active_docs)) or 0
    failed_jobs = (
        db.scalar(
            select(func.count()).where(
                IngestionJob.organization_id == org_id, IngestionJob.status == DocumentStatus.FAILED
            )
        )
        or 0
    )

    queries = select(SearchQuery).where(SearchQuery.organization_id == org_id).subquery()
    total_queries = db.scalar(select(func.count()).select_from(queries)) or 0
    success_rate = db.scalar(select(func.avg(cast(queries.c.success, Integer)))) if total_queries else None
    avg_retrieval = db.scalar(select(func.avg(queries.c.retrieval_ms)))

    answers = (Message.organization_id == org_id) & (Message.role == MessageRole.ASSISTANT)
    total_answers = db.scalar(select(func.count()).where(answers)) or 0
    avg_generation = db.scalar(
        select(func.avg(Message.generation_ms)).where(answers, Message.status == "answered")
    )
    avg_total = db.scalar(select(func.avg(Message.total_ms)).where(answers))
    abstained = db.scalar(select(func.count()).where(answers, Message.status == "abstained")) or 0
    validity = db.scalar(
        select(func.avg(cast(Message.verification["citation_validity"].astext, Float))).where(
            answers, Message.verification["citation_validity"].astext.is_not(None)
        )
    )
    coverage = db.scalar(
        select(func.avg(cast(Message.verification["evidence_coverage"].astext, Float))).where(
            answers, Message.verification["evidence_coverage"].astext.is_not(None)
        )
    )
    total_conversations = (
        db.scalar(
            select(func.count()).where(
                Conversation.organization_id == org_id, Conversation.deleted_at.is_(None)
            )
        )
        or 0
    )
    by_type = db.execute(
        select(Document.file_type, func.count()).where(active_docs).group_by(Document.file_type)
    ).all()
    by_status = db.execute(
        select(Document.status, func.count()).where(active_docs).group_by(Document.status)
    ).all()

    return {
        "documents": {
            "total": total_documents,
            "indexed": indexed,
            "processing": processing,
            "failed": failed_docs,
            "chunks": total_chunks,
            "storage_bytes": int(storage_bytes),
            "by_type": [{"name": t, "value": n} for t, n in by_type],
            "by_status": [{"name": s.value, "value": n} for s, n in by_status],
        },
        "failed_ingestion_jobs": failed_jobs,
        "queries": {
            "total": total_queries,
            "retrieval_success_rate": _round(success_rate, 4),
            "avg_retrieval_ms": _round(avg_retrieval),
        },
        "answers": {
            "total": total_answers,
            "abstained": abstained,
            "abstention_rate": round(abstained / total_answers, 4) if total_answers else None,
            "avg_generation_ms": _round(avg_generation),
            "avg_total_ms": _round(avg_total),
            "citation_validity_rate": _round(validity, 4),
            "evidence_coverage": _round(coverage, 4),
        },
        "conversations": total_conversations,
    }


def retrieval(db: Session, org_id: uuid.UUID, days: int = 30) -> dict[str, Any]:
    since = _since(days)
    base = (SearchQuery.organization_id == org_id) & (SearchQuery.created_at >= since)
    day = func.date_trunc("day", SearchQuery.created_at).cast(Date)
    latency = db.execute(
        select(
            day,
            func.avg(SearchQuery.retrieval_ms),
            func.percentile_cont(0.5).within_group(SearchQuery.retrieval_ms),
            func.percentile_cont(0.95).within_group(SearchQuery.retrieval_ms),
            func.count(),
        )
        .where(base)
        .group_by(day)
        .order_by(day)
    ).all()
    by_strategy = db.execute(
        select(
            SearchQuery.strategy,
            func.count(),
            func.avg(SearchQuery.retrieval_ms),
            func.percentile_cont(0.95).within_group(SearchQuery.retrieval_ms),
            func.avg(cast(SearchQuery.success, Integer)),
        )
        .where(base)
        .group_by(SearchQuery.strategy)
    ).all()
    by_kind = db.execute(select(SearchQuery.kind, func.count()).where(base).group_by(SearchQuery.kind)).all()

    # Average time per pipeline stage, from each query's timing breakdown (JSONB).
    stage = func.jsonb_each_text(SearchQuery.timings).table_valued("key", "value").lateral("stage")
    stage_rows = db.execute(
        select(stage.c.key, func.avg(cast(stage.c.value, Float)), func.count())
        .select_from(SearchQuery)
        .join(stage, literal(True))
        .where(base)
        .group_by(stage.c.key)
    ).all()

    message_day = func.date_trunc("day", Message.created_at).cast(Date)
    generation = db.execute(
        select(
            message_day,
            func.avg(Message.generation_ms),
            func.avg(Message.total_ms),
        )
        .where(
            Message.organization_id == org_id,
            Message.role == MessageRole.ASSISTANT,
            Message.created_at >= since,
            Message.status == "answered",
        )
        .group_by(message_day)
        .order_by(message_day)
    ).all()

    return {
        "days": days,
        "latency": [
            {
                "date": d.isoformat(),
                "avg_ms": _round(avg),
                "p50_ms": _round(p50),
                "p95_ms": _round(p95),
                "queries": n,
            }
            for d, avg, p50, p95, n in latency
        ],
        "response_latency": [
            {"date": d.isoformat(), "generation_ms": _round(g), "total_ms": _round(t)}
            for d, g, t in generation
        ],
        "by_strategy": [
            {
                "strategy": s,
                "queries": n,
                "avg_ms": _round(avg),
                "p95_ms": _round(p95),
                "success_rate": _round(rate, 4),
            }
            for s, n, avg, p95, rate in by_strategy
        ],
        "by_kind": [{"name": k, "value": n} for k, n in by_kind],
        "stage_ms": sorted(
            ({"stage": k, "avg_ms": round(float(avg), 2), "samples": n} for k, avg, n in stage_rows),
            key=lambda row: -row["avg_ms"],
        ),
    }


def usage(db: Session, org_id: uuid.UUID, days: int = 30) -> dict[str, Any]:
    since = _since(days)

    def daily(column, *conditions) -> list[dict[str, Any]]:  # type: ignore[no-untyped-def]
        d = func.date_trunc("day", column).cast(Date)
        rows = db.execute(select(d, func.count()).where(*conditions).group_by(d)).all()
        return _day_series(rows, days)

    queries = daily(
        SearchQuery.created_at, SearchQuery.organization_id == org_id, SearchQuery.created_at >= since
    )
    uploads = daily(Document.created_at, Document.organization_id == org_id, Document.created_at >= since)
    failures = daily(
        IngestionJob.created_at,
        IngestionJob.organization_id == org_id,
        IngestionJob.created_at >= since,
        IngestionJob.status == DocumentStatus.FAILED,
    )
    conversations = daily(
        Conversation.created_at, Conversation.organization_id == org_id, Conversation.created_at >= since
    )
    api_calls = daily(ApiUsage.created_at, ApiUsage.organization_id == org_id, ApiUsage.created_at >= since)
    token_day = func.date_trunc("day", Message.created_at).cast(Date)
    token_rows = db.execute(
        select(
            token_day,
            func.coalesce(func.sum(Message.prompt_tokens), 0),
            func.coalesce(func.sum(Message.completion_tokens), 0),
        )
        .where(
            Message.organization_id == org_id,
            Message.created_at >= since,
            Message.role == MessageRole.ASSISTANT,
        )
        .group_by(token_day)
    ).all()
    tokens = {d.isoformat(): (int(p), int(c)) for d, p, c in token_rows}
    active_users = (
        db.scalar(
            select(func.count(func.distinct(SearchQuery.user_id))).where(
                SearchQuery.organization_id == org_id, SearchQuery.created_at >= since
            )
        )
        or 0
    )

    series = []
    for i, row in enumerate(queries):
        p, c = tokens.get(row["date"], (0, 0))
        series.append(
            {
                "date": row["date"],
                "queries": row["value"],
                "uploads": uploads[i]["value"],
                "failures": failures[i]["value"],
                "conversations": conversations[i]["value"],
                "api_calls": api_calls[i]["value"],
                "prompt_tokens": p,
                "completion_tokens": c,
            }
        )
    return {"days": days, "active_users": active_users, "series": series}
