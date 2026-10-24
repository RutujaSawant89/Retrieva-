"""Overview questions: "what is this document about?", "summarize the file", "key points".

These ask about a document as a whole, so passage retrieval is the wrong tool: no single
passage is "relevant" to the question text, the reranker scores everything low, and the
abstention gate would refuse. Instead the answer is grounded in the document's opening passages
(title, introduction, first sections), read in document order, and still cited and verified.
"""

from __future__ import annotations

import re
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Document, DocumentChunk, DocumentStatus
from app.services.access import document_visibility_for
from app.services.generation.context import AssembledContext
from app.services.retrieval.analyzer import content_words
from app.services.retrieval.pipeline import RetrievalPipeline
from app.services.retrieval.types import Evidence, RetrievalScope
from app.services.text import split_sentences

PASSAGES_PER_DOCUMENT = 6
MAX_DOCUMENTS = 3

_DOC = r"(?:document|doc|file|pdf|report|paper|text|contract|policy|agreement|these|this|it|them)"
_OVERVIEW = re.compile(
    rf"\b(?:what(?:'s| is| are)?\s+(?:the|this|these|that|my)?\s*{_DOC}\s+(?:about|abt|for)"
    rf"|what\s+(?:does|do)\s+(?:the|this|these)?\s*{_DOC}\s+(?:say|contain|cover|describe|talk about)"
    r"|summar(?:y|ize|ise|izing|ising)|overview|tl;?dr|gist|outline"
    r"|(?:main|key)\s+(?:points|ideas|topics|takeaways|contents)"
    rf"|describe\s+(?:the|this)\s*{_DOC}|explain\s+(?:the|this)\s*{_DOC})\b",
    re.IGNORECASE,
)


def is_overview_question(question: str) -> bool:
    return bool(_OVERVIEW.search(question))


def choose_documents(
    db: Session, scope: RetrievalScope, hinted: list[uuid.UUID]
) -> tuple[list[uuid.UUID], str]:
    """Pick the document(s) an overview question refers to, and explain the choice.

    Order of preference: the conversation's scope, the only document the user can see, documents
    named in the question, then the most recently indexed document.
    """
    visible = select(Document.id, Document.title).where(
        document_visibility_for(scope.org_id, scope.user_id, scope.can_manage),
        Document.status == DocumentStatus.COMPLETED,
    )
    if scope.document_ids is not None:
        rows = db.execute(visible.where(Document.id.in_(scope.document_ids)).limit(MAX_DOCUMENTS)).all()
        if rows:
            return [r[0] for r in rows], "overview — the documents in this conversation's scope"
    rows = db.execute(visible.limit(2)).all()
    if len(rows) == 1:
        return [rows[0][0]], f"overview — '{rows[0][1]}' is the only document available"
    if hinted:
        return hinted[:MAX_DOCUMENTS], "overview — documents named in the question"
    latest = db.execute(visible.order_by(Document.indexed_at.desc().nulls_last()).limit(1)).first()
    if latest is None:
        return [], "overview — no indexed documents"
    return [latest[0]], f"overview — the most recently uploaded document, '{latest[1]}'"


def opening_passages(db: Session, scope: RetrievalScope, document_ids: list[uuid.UUID]) -> list[Evidence]:
    """The first passages of each document, in reading order."""
    chunk_ids: list[uuid.UUID] = []
    for document_id in document_ids:
        chunk_ids += list(
            db.scalars(
                select(DocumentChunk.id)
                .where(
                    DocumentChunk.document_id == document_id, DocumentChunk.organization_id == scope.org_id
                )
                .order_by(DocumentChunk.chunk_index)
                .limit(PASSAGES_PER_DOCUMENT)
            )
        )
    evidence = RetrievalPipeline._load(db, scope, chunk_ids)
    for rank, item in enumerate(evidence, start=1):
        item.final_rank = rank
    return evidence


def overview_instruction(question: str) -> str:
    return (
        f"{question}\n\n(This is a request for an overview. Using the sources, which are the opening "
        "passages of the document(s), say what kind of document it is, its purpose, and its main "
        "contents. Cite every statement.)"
    )


def extractive_overview(context: AssembledContext, max_sentences: int = 5) -> str | None:
    """LLM-free overview: the leading informative sentences of the opening passages, cited."""
    # Titles go on their own line: a cited sentence must contain only text from its source.
    sections: dict[str, list[str]] = {}
    count = 0
    for item in context.items:
        if count >= max_sentences:
            break
        for sentence in split_sentences(item.text):
            if len(content_words(sentence)) < 4:
                continue
            sections.setdefault(item.document_title, []).append(f"{sentence.rstrip()} [{item.label}]")
            count += 1
            break  # one sentence per passage keeps the summary broad
    if not sections:
        return None
    return "\n\n".join(f"**{title}**\n\n{' '.join(lines)}" for title, lines in sections.items())
