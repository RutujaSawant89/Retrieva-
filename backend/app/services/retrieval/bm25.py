"""Okapi BM25 over an in-memory inverted index.

score(q, d) = Σ_t IDF(t) · tf(t,d)·(k1+1) / (tf(t,d) + k1·(1 − b + b·|d|/avgdl))
IDF(t)      = ln(1 + (N − df(t) + 0.5) / (df(t) + 0.5))        (Lucene's non-negative variant)

Query term weights are supported so expansion terms (pseudo-relevance feedback) can count less
than the user's own terms.
"""

from __future__ import annotations

import math
from collections import Counter
from collections.abc import Hashable, Sequence

import numpy as np

from app.services.retrieval.analyzer import analyze


class BM25Index:
    def __init__(
        self, ids: Sequence[Hashable], texts: Sequence[str], k1: float = 1.2, b: float = 0.75
    ) -> None:
        if len(ids) != len(texts):
            raise ValueError("ids and texts must have the same length")
        self.k1 = k1
        self.b = b
        self.ids = list(ids)
        self.position = {doc_id: i for i, doc_id in enumerate(self.ids)}
        self.n_docs = len(self.ids)
        self.doc_len = np.zeros(self.n_docs, dtype=np.float32)
        postings: dict[str, tuple[list[int], list[int]]] = {}
        self.forward: list[Counter[str]] = []
        for i, text in enumerate(texts):
            terms = analyze(text)
            self.doc_len[i] = len(terms)
            counts = Counter(terms)
            self.forward.append(counts)
            for term, tf in counts.items():
                docs, tfs = postings.setdefault(term, ([], []))
                docs.append(i)
                tfs.append(tf)
        self.postings = {
            term: (np.asarray(docs, dtype=np.int32), np.asarray(tfs, dtype=np.float32))
            for term, (docs, tfs) in postings.items()
        }
        self.avgdl = float(self.doc_len.mean()) if self.n_docs else 0.0
        self._norm = self.k1 * (1 - self.b + self.b * self.doc_len / max(self.avgdl, 1e-9))

    def idf(self, term: str) -> float:
        df = len(self.postings[term][0]) if term in self.postings else 0
        return math.log(1 + (self.n_docs - df + 0.5) / (df + 0.5))

    def scores(self, weighted_terms: dict[str, float]) -> np.ndarray:
        scores = np.zeros(self.n_docs, dtype=np.float32)
        for term, weight in weighted_terms.items():
            entry = self.postings.get(term)
            if entry is None:
                continue
            docs, tfs = entry
            contribution = self.idf(term) * tfs * (self.k1 + 1) / (tfs + self._norm[docs])
            scores[docs] += weight * contribution
        return scores

    def search(
        self,
        query: str | dict[str, float],
        top_k: int = 10,
        allowed: np.ndarray | None = None,
    ) -> list[tuple[Hashable, float]]:
        """Return ``(id, score)`` pairs, best first. ``allowed`` is a boolean mask over documents."""
        if self.n_docs == 0:
            return []
        weighted = query if isinstance(query, dict) else dict(Counter(analyze(query)))
        if not weighted:
            return []
        scores = self.scores(weighted)
        if allowed is not None:
            scores = np.where(allowed, scores, 0.0)
        candidates = np.flatnonzero(scores > 0)
        if candidates.size == 0:
            return []
        k = min(top_k, candidates.size)
        top = candidates[np.argpartition(-scores[candidates], k - 1)[:k]]
        top = top[np.argsort(-scores[top], kind="stable")]
        return [(self.ids[i], float(scores[i])) for i in top]

    def term_frequencies(self, doc_id: Hashable) -> Counter[str]:
        """Terms of one indexed document (used for pseudo-relevance feedback)."""
        return self.forward[self.position[doc_id]]
