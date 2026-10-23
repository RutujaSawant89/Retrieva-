"""Evaluation runs: execute a dataset against one retrieval configuration and store the metrics.

Every number stored here is computed from an actual execution of the pipeline on the
organization's indexed documents; nothing is estimated. Runs are reproducible from the stored
dataset version, retrieval configuration and model versions.
"""

from __future__ import annotations

import logging
import time
import uuid
from datetime import UTC, datetime
from typing import Any

import numpy as np
from sqlalchemy import select

from app.core.permissions import Permission, has_permission
from app.db.models import (
    Document,
    EvaluationDataset,
    EvaluationResult,
    EvaluationRun,
    OrganizationMember,
    Role,
    RunStatus,
)
from app.db.session import session_scope
from app.services.citations.verifier import SUPPORTED, get_support_scorer, get_verifier
from app.services.embeddings.service import get_embedding_service
from app.services.evaluation import metrics as m
from app.services.evaluation.ragas_adapter import ragas_scores
from app.services.generation.context import assemble
from app.services.generation.engine import abstention_gate
from app.services.generation.extractive import extractive_answer
from app.services.generation.prompts import ABSTAIN_MARKER, build_messages
from app.services.generation.providers import LLMError, get_llm
from app.services.retrieval.pipeline import RetrievalPipeline, log_query
from app.services.retrieval.types import RetrievalConfig, RetrievalScope
from app.services.text import split_sentences

logger = logging.getLogger(__name__)

DEFAULT_KS = (1, 3, 5, 10)


def _scope_for(db, run: EvaluationRun) -> RetrievalScope:  # type: ignore[no-untyped-def]
    role = db.scalar(
        select(Role.name)
        .join(OrganizationMember, OrganizationMember.role_id == Role.id)
        .where(
            OrganizationMember.organization_id == run.organization_id,
            OrganizationMember.user_id == run.created_by,
        )
    )
    doc_ids = run.config.get("document_ids") or None
    return RetrievalScope(
        org_id=run.organization_id,
        user_id=run.created_by,  # type: ignore[arg-type]
        can_manage=has_permission(role or "", Permission.DOCUMENTS_MANAGE),
        document_ids=tuple(uuid.UUID(d) for d in doc_ids) if doc_ids else None,
    )


def _generate(question: str, evidence: list, scope: RetrievalScope, result) -> tuple[str | None, Any]:  # type: ignore[no-untyped-def]
    decision = abstention_gate(result)
    if decision.abstain:
        return None, None
    context = assemble(evidence, 2400)
    llm = get_llm()
    if llm is None:
        return extractive_answer(question, context, get_embedding_service()), context
    try:
        text, _ = llm.complete(build_messages(question, context), max_tokens=600, temperature=0.0)
    except LLMError as exc:
        logger.warning("eval_generation_failed", extra={"error": str(exc)})
        return None, context
    text = text.strip()
    return (None if text.startswith(ABSTAIN_MARKER) else text), context


def _supported_fraction(sentences: list[str], passages: list, scorer) -> float | None:  # type: ignore[no-untyped-def]
    sentences = [s for s in sentences if len(s.split()) >= 4]
    if not sentences or not passages:
        return None
    supported = sum(1 for s in sentences if max(scorer.score(s, passages), default=0.0) >= SUPPORTED)
    return supported / len(sentences)


def evaluate_item(
    db,
    scope: RetrievalScope,
    item: dict[str, Any],
    config: RetrievalConfig,
    ks: tuple[int, ...],
    generate: bool,
) -> dict[str, Any]:  # type: ignore[no-untyped-def]
    started = time.perf_counter()
    result = RetrievalPipeline().run(db, scope, item["question"], config)
    log_query(db, scope, result, "eval")
    retrieved = result.evidence
    titles = {d.lower() for d in item.get("relevant_documents", [])}
    passages = item.get("relevant_passages", [])

    def relevant(e) -> bool:  # type: ignore[no-untyped-def]
        return any(m.passage_matches(p, e.content) for p in passages) or e.document_title.lower() in titles

    relevance = [relevant(e) for e in retrieved]
    if passages:
        found = [
            next((r for r, e in enumerate(retrieved, 1) if m.passage_matches(p, e.content)), None)
            for p in passages
        ]
    else:
        found = [
            next((r for r, e in enumerate(retrieved, 1) if e.document_title.lower() == t), None)
            for t in titles
        ]
    # nDCG gains: only the first retrieved item satisfying each labelled target earns gain, so a
    # target split across overlapping chunks is not double-counted and nDCG stays within [0, 1].
    first_hits = {rank for rank in found if rank is not None}
    gains = [1.0 if rank in first_hits else 0.0 for rank in range(1, len(retrieved) + 1)]
    ideal = [1.0] * len(found)

    scores: dict[str, Any] = {
        "mrr": m.reciprocal_rank(relevance),
        "context_precision": m.context_precision(relevance),
        "retrieval_ms": result.total_ms,
        "hit": any(relevance),
    }
    for k in ks:
        scores[f"precision@{k}"] = m.precision_at_k(relevance, k)
        scores[f"recall@{k}"] = m.recall_at_k(found, k)
        scores[f"ndcg@{k}"] = m.ndcg_at_k(gains, k, ideal_gains=ideal)

    answer = None
    if generate:
        answer, context = _generate(item["question"], retrieved, scope, result)
        scorer = get_support_scorer()
        scores["abstained"] = answer is None
        if answer and context is not None:
            report = get_verifier().verify(answer, context)
            scores["citation_precision"] = report.citation_precision
            scores["citation_coverage"] = report.evidence_coverage
            claims = [c.text for c in report.claims]
            scores["faithfulness"] = _supported_fraction(claims, context.items, scorer)
            embedder = get_embedding_service()
            q, a = embedder.embed_query(item["question"]), embedder.embed_documents([answer])[0]
            scores["answer_relevancy"] = round(float(np.clip(q @ a, 0.0, 1.0)), 4)
        if item.get("reference_answer"):
            scores["context_recall"] = _supported_fraction(
                split_sentences(item["reference_answer"]), retrieved, scorer
            )
    return {
        "scores": scores,
        "answer": answer,
        "retrieved": [
            {
                "rank": e.final_rank,
                "chunk_id": str(e.chunk_id),
                "document_title": e.document_title,
                "page": e.page_number,
                "relevant": rel,
                "score": e.primary_score,
                "excerpt": e.content[:300],
            }
            for e, rel in zip(retrieved, relevance, strict=True)
        ],
        "latency_ms": round((time.perf_counter() - started) * 1000, 1),
    }


def aggregate(rows: list[dict[str, Any]]) -> dict[str, Any]:
    keys = sorted(
        {k for row in rows for k, v in row.items() if isinstance(v, int | float) and not isinstance(v, bool)}
    )
    out: dict[str, Any] = {k: m.mean([row.get(k) for row in rows]) for k in keys}
    out["hit_rate"] = m.mean([1.0 if row.get("hit") else 0.0 for row in rows])
    if any("abstained" in row for row in rows):
        out["abstention_rate"] = m.mean([1.0 if row.get("abstained") else 0.0 for row in rows])
    latencies = sorted(row["retrieval_ms"] for row in rows if row.get("retrieval_ms") is not None)
    if latencies:
        out["retrieval_ms_p95"] = round(float(np.percentile(latencies, 95)), 1)
    out["items"] = len(rows)
    return out


def run_evaluation(run_id: uuid.UUID, org_id: uuid.UUID) -> None:
    with session_scope(org_id) as db:
        run = db.get(EvaluationRun, run_id)
        if run is None:
            return
        dataset = db.get(EvaluationDataset, run.dataset_id)
        run.status = RunStatus.RUNNING
        run.started_at = datetime.now(UTC)
        db.commit()
        try:
            scope = _scope_for(db, run)
            options = dict(run.config.get("retrieval", {}))
            ks = tuple(sorted(set(run.config.get("ks") or DEFAULT_KS)))
            options["top_k"] = max(options.get("top_k", 10), max(ks))
            config = RetrievalConfig(**options)
            generate = bool(run.config.get("generate"))
            if not db.scalar(select(Document.id).where(Document.organization_id == org_id).limit(1)):
                raise ValueError("The organization has no documents to evaluate against")
            rows = []
            qa_records = []
            for index, item in enumerate(dataset.items):  # type: ignore[union-attr]
                outcome = evaluate_item(db, scope, item, config, ks, generate)
                rows.append(outcome["scores"])
                db.add(
                    EvaluationResult(
                        organization_id=org_id,
                        run_id=run.id,
                        item_index=index,
                        question=item["question"],
                        retrieved=outcome["retrieved"],
                        answer=outcome["answer"],
                        metrics=outcome["scores"],
                        latency_ms=outcome["latency_ms"],
                    )
                )
                qa_records.append((item, outcome))
                db.commit()
            summary = aggregate(rows)
            if run.config.get("use_ragas") and generate:
                summary["ragas"] = ragas_scores(qa_records)
            run.metrics = summary
            run.status = RunStatus.COMPLETED
        except Exception as exc:
            db.rollback()
            logger.exception("evaluation_failed", extra={"run_id": str(run_id)})
            run = db.get(EvaluationRun, run_id)
            run.status = RunStatus.FAILED  # type: ignore[union-attr]
            run.error_message = str(exc)[:1000]  # type: ignore[union-attr]
        run.finished_at = datetime.now(UTC)  # type: ignore[union-attr]
        db.commit()
