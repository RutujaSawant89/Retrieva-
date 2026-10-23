"""Query understanding: normalisation, follow-up resolution, rewriting, multi-query, expansion.

Techniques are applied selectively by ``plan()``; each decision is recorded so the UI and the
evaluation framework can show *why* a query was transformed.
"""

from __future__ import annotations

import logging
import re
from collections import Counter
from dataclasses import dataclass, field

from app.services.generation.providers import ChatMessage, LLMError, get_llm
from app.services.retrieval.analyzer import STOP_WORDS, analyze
from app.services.retrieval.bm25 import BM25Index

logger = logging.getLogger(__name__)

MAX_QUERY_CHARS = 2000
_FOLLOW_UP = re.compile(
    r"^(and|also|what about|how about|then|so|but|why|how come)\b|\b(it|its|they|them|their|this|that|these|those|"
    r"he|she|his|her|the same|above|previous|former|latter)\b",
    re.I,
)
_COMPLEX = re.compile(
    r"\b(compare|versus|vs\.?|difference|differences|both|each|respectively|and also)\b", re.I
)


@dataclass
class QueryPlan:
    original: str
    normalized: str
    search_query: str  # standalone version used for retrieval
    variants: list[str] = field(default_factory=list)  # additional queries (multi-query)
    expansion_terms: dict[str, float] = field(default_factory=dict)
    decisions: list[str] = field(default_factory=list)

    @property
    def all_queries(self) -> list[str]:
        return [self.search_query, *[v for v in self.variants if v != self.search_query]]


def normalize_query(query: str) -> str:
    query = query.replace("\x00", "").strip()
    query = re.sub(r"\s+", " ", query)
    return query[:MAX_QUERY_CHARS]


def looks_like_follow_up(query: str) -> bool:
    words = query.split()
    return bool(_FOLLOW_UP.search(query)) or len(words) <= 3


def _llm_rewrite(query: str, history: list[tuple[str, str]]) -> str | None:
    llm = get_llm()
    if llm is None:
        return None
    transcript = "\n".join(f"{role.upper()}: {text[:600]}" for role, text in history[-6:])
    messages = [
        ChatMessage(
            "system",
            "You rewrite the user's latest message into a standalone search query for a document search "
            "engine. Resolve pronouns and references using the conversation. Output only the query, no "
            "explanations. Never answer the question.",
        ),
        ChatMessage("user", f"Conversation:\n{transcript}\n\nLatest message: {query}\n\nStandalone query:"),
    ]
    try:
        text, _ = llm.complete(messages, max_tokens=80, temperature=0.0)
    except LLMError:
        logger.warning("llm_rewrite_failed", exc_info=True)
        return None
    text = text.strip().strip('"').splitlines()[0].strip() if text.strip() else ""
    return text[:MAX_QUERY_CHARS] or None


def _heuristic_rewrite(query: str, history: list[tuple[str, str]]) -> str:
    """Attach the key terms of the previous user question to an under-specified follow-up."""
    previous = next((text for role, text in reversed(history) if role == "user"), "")
    if not previous:
        return query
    prev_terms = [
        w for w in re.findall(r"[A-Za-z0-9][A-Za-z0-9\-]*", previous) if w.lower() not in STOP_WORDS
    ]
    current = {w.lower() for w in query.split()}
    carry = [w for w in prev_terms if w.lower() not in current][:8]
    return f"{query} {' '.join(carry)}".strip()


def _llm_variants(query: str, n: int = 3) -> list[str]:
    llm = get_llm()
    if llm is None:
        return []
    messages = [
        ChatMessage(
            "system",
            f"Generate {n} alternative search queries that would retrieve documents answering the user's "
            "question. Vary vocabulary and decompose multi-part questions. One query per line, no numbering, "
            "no commentary.",
        ),
        ChatMessage("user", query),
    ]
    try:
        text, _ = llm.complete(messages, max_tokens=160, temperature=0.3)
    except LLMError:
        logger.warning("llm_multi_query_failed", exc_info=True)
        return []
    lines = [re.sub(r"^[\s\-*\d.)]+", "", ln).strip() for ln in text.splitlines()]
    return [ln[:300] for ln in lines if len(ln) > 3][:n]


def heuristic_variants(query: str) -> list[str]:
    """Without an LLM: split compound questions and add a keyword-only form."""
    parts = [
        p.strip()
        for p in re.split(r"\?|;|\band\b(?=\s+(?:what|how|why|when|who|which|is|are|does|do)\b)", query)
        if p and len(p.strip()) > 8
    ]
    keywords = " ".join(
        w for w in re.findall(r"[A-Za-z0-9][A-Za-z0-9\-.]*", query) if w.lower() not in STOP_WORDS
    )
    variants = [p for p in parts if p != query] if len(parts) > 1 else []
    if keywords and keywords.lower() != query.lower():
        variants.append(keywords)
    return variants[:3]


def pseudo_relevance_feedback(
    index: BM25Index, feedback_ids: list, query: str, n_terms: int = 6, weight: float = 0.3
) -> dict[str, float]:
    """RM3-style expansion: frequent, discriminative terms from top-ranked passages.

    Expansion terms receive a lower weight than the original query terms.
    """
    query_terms = set(analyze(query))
    pool: Counter[str] = Counter()
    for chunk_id in feedback_ids:
        tf = index.term_frequencies(chunk_id)
        total = sum(tf.values()) or 1
        for term, count in tf.items():
            if term in query_terms or term.isdigit() or len(term) < 3:
                continue
            pool[term] += (count / total) * index.idf(term)
    return {term: weight for term, _ in pool.most_common(n_terms)}


def plan(
    query: str,
    history: list[tuple[str, str]] | None = None,
    *,
    rewrite: bool | str = "auto",
    multi_query: bool | str = "auto",
) -> QueryPlan:
    history = history or []
    normalized = normalize_query(query)
    result = QueryPlan(original=query, normalized=normalized, search_query=normalized)

    should_rewrite = rewrite is True or (rewrite == "auto" and history and looks_like_follow_up(normalized))
    if should_rewrite and history:
        rewritten = _llm_rewrite(normalized, history)
        method = "llm"
        if not rewritten:
            rewritten = _heuristic_rewrite(normalized, history)
            method = "heuristic"
        if rewritten and rewritten != normalized:
            result.search_query = rewritten
            result.decisions.append(f"rewrite:{method} — follow-up resolved to a standalone query")
    elif rewrite == "auto" and history:
        result.decisions.append("rewrite:skipped — query is already standalone")

    should_multi = multi_query is True or (
        multi_query == "auto"
        and (_COMPLEX.search(normalized) or normalized.count("?") > 1 or len(normalized.split()) > 18)
    )
    if should_multi:
        variants = _llm_variants(result.search_query)
        method = "llm"
        if not variants:
            variants = heuristic_variants(result.search_query)
            method = "heuristic"
        if variants:
            result.variants = variants
            result.decisions.append(f"multi_query:{method} — {len(variants)} additional queries")
    return result
