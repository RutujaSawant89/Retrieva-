"""Answer engine: retrieval → abstention gate → context → generation → verification → storage.

``answer_events`` yields a sequence of events used both by the streaming endpoint (as SSE) and
by the non-streaming endpoint (collected into a single response):

    meta → retrieval → token* → verification → done      (or error at any point)
"""

from __future__ import annotations

import logging
import time
import uuid
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from app.core.config import get_settings
from app.core.metrics import ABSTENTIONS
from app.db.models import Conversation, Message, MessageCitation, MessageRole
from app.db.session import session_scope
from app.services.citations.verifier import VerificationReport, get_verifier
from app.services.embeddings.service import get_embedding_service
from app.services.generation import memory
from app.services.generation.context import AssembledContext, assemble, location
from app.services.generation.extractive import extractive_answer
from app.services.generation.prompts import ABSTAIN_MARKER, build_messages
from app.services.generation.providers import LLMError, Usage, get_llm
from app.services.retrieval.pipeline import RetrievalPipeline, log_query
from app.services.retrieval.types import Evidence, RetrievalConfig, RetrievalResult, RetrievalScope

logger = logging.getLogger(__name__)

Event = tuple[str, dict[str, Any]]


@dataclass
class AbstentionDecision:
    abstain: bool
    reason: str | None = None
    message: str | None = None


def abstention_gate(result: RetrievalResult) -> AbstentionDecision:
    """Decide *before* generation whether the evidence can support an answer at all."""
    settings = get_settings()
    if not result.evidence:
        return AbstentionDecision(
            True,
            "no_evidence",
            "I couldn't find any passages in your accessible documents related to this question.",
        )
    best = result.evidence[0]
    if best.rerank_score is not None and result.reranker:
        threshold = (
            settings.lexical_abstain_threshold
            if result.reranker.startswith("lexical")
            else settings.rerank_abstain_threshold
        )
        if best.rerank_score < threshold:
            return AbstentionDecision(
                True,
                "low_relevance",
                "The closest passages I found don't appear to address this question, so I won't answer from them.",
            )
    return AbstentionDecision(False)


def evidence_payload(item: Evidence) -> dict[str, Any]:
    return {
        "label": item.label,
        "chunk_id": str(item.chunk_id),
        "document_id": str(item.document_id),
        "document_title": item.document_title,
        "file_type": item.file_type,
        "page_number": item.page_number,
        "page_end": item.page_end,
        "section": item.section,
        "location": location(item),
        "content": item.content,
        "compressed": item.compressed,
        "start_char": item.start_char,
        "end_char": item.end_char,
        "scores": {
            "dense": item.dense_score,
            "sparse": item.sparse_score,
            "fusion": item.fusion_score,
            "rerank": item.rerank_score,
        },
        "ranks": {"dense": item.dense_rank, "sparse": item.sparse_rank, "final": item.final_rank},
    }


def retrieval_payload(result: RetrievalResult, context: AssembledContext | None) -> dict[str, Any]:
    return {
        "queries": result.queries,
        "decisions": result.decisions,
        "timings_ms": result.timings_ms,
        "total_ms": result.total_ms,
        "candidates_considered": result.candidates_considered,
        "reranker": result.reranker,
        "embedding_model": result.embedding_model,
        "config": result.config.to_dict(),
        "conflicts": [
            {"labels": list(c.labels), "reason": c.reason} for c in (context.conflicts if context else [])
        ],
        "suspicious_sources": context.suspicious_labels if context else [],
        "dropped_for_budget": context.dropped_for_budget if context else 0,
    }


@dataclass
class AnswerRequest:
    scope: RetrievalScope
    question: str
    conversation_id: uuid.UUID
    config: RetrievalConfig = field(default_factory=RetrievalConfig)
    kind: str = "chat"
    regenerate_of: uuid.UUID | None = None  # assistant message being regenerated


def answer_events(req: AnswerRequest) -> Iterator[Event]:
    """Run the full answer flow, persisting messages, and yield progress events."""
    settings = get_settings()
    started = time.perf_counter()
    llm = None
    try:
        llm = get_llm()
    except LLMError as exc:
        yield "error", {"code": "llm_misconfigured", "message": str(exc)}
        return

    with session_scope(req.scope.org_id) as db:
        conversation = db.get(Conversation, req.conversation_id)
        if conversation is None or conversation.user_id != req.scope.user_id or conversation.deleted_at:
            yield "error", {"code": "not_found", "message": "Conversation not found"}
            return

        history = memory.recent_turns(db, conversation, exclude_message_id=req.regenerate_of)
        if req.regenerate_of is None:
            user_message = Message(
                organization_id=req.scope.org_id,
                conversation_id=conversation.id,
                role=MessageRole.USER,
                content=req.question,
            )
            db.add(user_message)
            if conversation.title == "New conversation":
                conversation.title = memory.title_from(req.question)
            db.flush()
        else:
            # Regeneration replaces the previous assistant answer for the same question.
            old = db.get(Message, req.regenerate_of)
            if old is not None and old.conversation_id == conversation.id:
                db.delete(old)
                db.flush()
        conversation.updated_at = datetime.now(UTC)
        db.commit()
        yield "meta", {"conversation_id": str(conversation.id), "title": conversation.title}

        # 1. Retrieval --------------------------------------------------------------------------
        pipeline = RetrievalPipeline()
        try:
            result = pipeline.run(db, req.scope, req.question, req.config, history=history)
        except Exception:
            logger.exception("retrieval_failed")
            yield "error", {"code": "retrieval_failed", "message": "Retrieval failed. Please try again."}
            return
        retrieval_ms = result.total_ms

        decision = abstention_gate(result)
        context = None if decision.abstain else assemble(result.evidence, settings.context_token_budget)
        if decision.abstain:
            # Still show the closest passages so the user can see why.
            for i, item in enumerate(result.evidence, start=1):
                item.label = f"S{i}"
        yield (
            "retrieval",
            {
                **retrieval_payload(result, context),
                "evidence": [evidence_payload(e) for e in (context.items if context else result.evidence)],
            },
        )

        # 2. Generation -------------------------------------------------------------------------
        db.commit()  # release the connection while the LLM streams
        usage = Usage()
        gen_started = time.perf_counter()
        answer = ""
        status = "answered"
        provider_name = llm.name if llm else "extractive"
        model_name = llm.model if llm else "extractive-v1"

        if decision.abstain:
            status = "abstained"
            answer = decision.message or "I don't have enough evidence to answer this question."
            ABSTENTIONS.labels(decision.reason or "unknown").inc()
            yield "token", {"delta": answer}
        elif llm is None:
            text = extractive_answer(req.question, context, get_embedding_service())  # type: ignore[arg-type]
            if text is None:
                status = "abstained"
                decision = AbstentionDecision(True, "no_matching_sentences")
                answer = "The retrieved passages don't contain sentences that answer this question."
                ABSTENTIONS.labels("no_matching_sentences").inc()
            else:
                answer = text
            yield "token", {"delta": answer}
        else:
            messages = build_messages(
                req.question,
                context,
                history,
                memory_summary=conversation.summary,  # type: ignore[arg-type]
            )
            pieces: list[str] = []
            try:
                for delta in llm.stream(
                    messages,
                    max_tokens=settings.llm_max_tokens,
                    temperature=settings.llm_temperature,
                    usage=usage,
                ):
                    pieces.append(delta)
                    yield "token", {"delta": delta}
                llm._record(gen_started, usage)
            except LLMError as exc:
                logger.warning("generation_failed", extra={"error": str(exc)})
                yield (
                    "error",
                    {
                        "code": "generation_failed",
                        "message": "The language model request failed. " + str(exc)[:200],
                    },
                )
                status = "error"
            answer = "".join(pieces).strip()
            if answer.startswith(ABSTAIN_MARKER):
                status = "abstained"
                decision = AbstentionDecision(True, "model_abstained")
                answer = (
                    answer[len(ABSTAIN_MARKER) :].lstrip(": ").strip()
                    or "The sources don't contain enough information."
                )
                ABSTENTIONS.labels("model_abstained").inc()
        generation_ms = round((time.perf_counter() - gen_started) * 1000, 1)

        # 3. Verification -----------------------------------------------------------------------
        report: VerificationReport | None = None
        if status == "answered" and context is not None and answer:
            try:
                report = get_verifier().verify(answer, context)
            except Exception:
                logger.exception("verification_failed")
        verification = report.to_dict() if report else {}
        if report is not None:
            yield "verification", verification

        # 4. Persist ----------------------------------------------------------------------------
        total_ms = round((time.perf_counter() - started) * 1000, 1)
        assistant = Message(
            organization_id=req.scope.org_id,
            conversation_id=conversation.id,
            role=MessageRole.ASSISTANT,
            content=answer,
            status=status,
            retrieval={
                **retrieval_payload(result, context),
                "abstention_reason": decision.reason,
            },
            verification=verification,
            llm_provider=provider_name,
            llm_model=model_name,
            prompt_tokens=usage.prompt_tokens or None,
            completion_tokens=usage.completion_tokens or None,
            retrieval_ms=retrieval_ms,
            generation_ms=generation_ms,
            total_ms=total_ms,
        )
        db.add(assistant)
        db.flush()
        items = context.items if context else result.evidence
        supporting = set(report.supporting_labels) if report else set()
        cited = set(report.cited_labels) if report else set()
        for index, item in enumerate(items, start=1):
            if item.label in cited:
                validation = "valid" if item.label in supporting else "weak"
            else:
                validation = "uncited"
            best_support = None
            if report:
                values = [c.support.get(item.label) for c in report.claims if item.label in c.support]
                best_support = max(values) if values else None
            db.add(
                MessageCitation(
                    organization_id=req.scope.org_id,
                    message_id=assistant.id,
                    label=item.label,
                    label_index=index,
                    chunk_id=item.chunk_id,
                    document_id=item.document_id,
                    document_title=item.document_title[:500],
                    page_number=item.page_number,
                    section=item.section,
                    passage=item.content,
                    retrieval_score=item.fusion_score if item.fusion_score is not None else item.dense_score,
                    rerank_score=item.rerank_score,
                    cited_in_answer=item.label in cited,
                    validation_status=validation,
                    support_score=best_support,
                )
            )
        log_query(db, req.scope, result, req.kind, success=status == "answered")
        conversation.updated_at = datetime.now(UTC)
        db.commit()
        memory.maybe_summarize(db, conversation)
        db.commit()

        yield (
            "done",
            {
                "message_id": str(assistant.id),
                "status": status,
                "abstention_reason": decision.reason,
                "llm_provider": provider_name,
                "llm_model": model_name,
                "retrieval_ms": retrieval_ms,
                "generation_ms": generation_ms,
                "total_ms": total_ms,
                "prompt_tokens": usage.prompt_tokens,
                "completion_tokens": usage.completion_tokens,
            },
        )
