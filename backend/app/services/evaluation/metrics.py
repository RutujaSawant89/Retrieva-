"""Retrieval and RAG evaluation metrics.

Information-retrieval metrics (binary relevance unless graded gains are given):

* Precision@K = |relevant ∩ top-K| / K
* Recall@K    = |relevant targets found in top-K| / |relevant targets|
* MRR         = 1 / rank of the first relevant result (0 if none)
* nDCG@K      = DCG@K / IDCG@K, DCG = Σ (2^gain − 1) / log2(rank + 1)

RAG metrics (RAGAS-style definitions, computed with Retrieva's own verifier):

* Context precision = Σ_k (Precision@k · rel_k) / |relevant in top-K|   (rank-aware precision)
* Context recall    = share of reference-answer sentences supported by the retrieved contexts
* Faithfulness      = share of answer claims supported by the retrieved contexts
* Answer relevancy  = cosine(question embedding, answer embedding) — an embedding-based
                      approximation of RAGAS answer relevancy (no question generation)
* Citation precision / coverage = from the citation verifier (see services/citations)
"""

from __future__ import annotations

import math
import re
from collections.abc import Sequence

_WS = re.compile(r"\s+")
_NON_WORD = re.compile(r"[^\w\s]")


def precision_at_k(relevance: Sequence[bool], k: int) -> float:
    if k <= 0:
        raise ValueError("k must be positive")
    return sum(1 for r in relevance[:k] if r) / k


def recall_at_k(found_targets_at: Sequence[int | None], k: int) -> float:
    """``found_targets_at[i]`` is the 1-based rank at which target i was first retrieved (None if never)."""
    if not found_targets_at:
        return 0.0
    return sum(1 for rank in found_targets_at if rank is not None and rank <= k) / len(found_targets_at)


def reciprocal_rank(relevance: Sequence[bool]) -> float:
    for rank, relevant in enumerate(relevance, start=1):
        if relevant:
            return 1.0 / rank
    return 0.0


def dcg(gains: Sequence[float], k: int) -> float:
    return sum((2**g - 1) / math.log2(rank + 1) for rank, g in enumerate(gains[:k], start=1))


def ndcg_at_k(gains: Sequence[float], k: int, ideal_gains: Sequence[float] | None = None) -> float:
    ideal = sorted(ideal_gains if ideal_gains is not None else gains, reverse=True)
    best = dcg(ideal, k)
    return dcg(gains, k) / best if best > 0 else 0.0


def context_precision(relevance: Sequence[bool]) -> float:
    relevant = sum(1 for r in relevance if r)
    if relevant == 0:
        return 0.0
    total = 0.0
    hits = 0
    for k, rel in enumerate(relevance, start=1):
        if rel:
            hits += 1
            total += hits / k
    return total / relevant


def normalize(text: str) -> str:
    return _WS.sub(" ", _NON_WORD.sub(" ", text.lower())).strip()


def passage_matches(target: str, retrieved: str, token_overlap: float = 0.8) -> bool:
    """A labelled passage counts as retrieved if it is contained in the chunk, either verbatim
    (after normalisation) or with at least ``token_overlap`` of its tokens present — robust to
    chunk boundaries and extraction whitespace differences."""
    t, r = normalize(target), normalize(retrieved)
    if not t:
        return False
    if t in r:
        return True
    target_tokens = t.split()
    retrieved_tokens = set(r.split())
    return sum(1 for tok in target_tokens if tok in retrieved_tokens) / len(target_tokens) >= token_overlap


def mean(values: Sequence[float | None]) -> float | None:
    present = [v for v in values if v is not None]
    return round(sum(present) / len(present), 4) if present else None
