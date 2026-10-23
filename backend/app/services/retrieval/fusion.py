"""Reciprocal Rank Fusion (Cormack, Clarke & Büttcher, 2009).

RRF(d) = Σ_r  w_r / (k + rank_r(d))      with 1-based ranks; documents absent from a ranking
contribute nothing for it. RRF only uses ranks, so it fuses retrievers whose scores live on
incomparable scales (cosine similarity vs. BM25) without score normalisation.
"""

from __future__ import annotations

from collections.abc import Hashable, Sequence


def reciprocal_rank_fusion(
    rankings: dict[str, Sequence[Hashable]],
    k: int = 60,
    weights: dict[str, float] | None = None,
) -> list[tuple[Hashable, float]]:
    if k < 1:
        raise ValueError("k must be >= 1")
    weights = weights or {}
    scores: dict[Hashable, float] = {}
    first_seen: dict[Hashable, tuple[int, int]] = {}
    for order, (name, ranking) in enumerate(rankings.items()):
        weight = weights.get(name, 1.0)
        if weight <= 0:
            continue
        for rank, item in enumerate(ranking, start=1):
            scores[item] = scores.get(item, 0.0) + weight / (k + rank)
            first_seen.setdefault(item, (rank, order))
    # Ties break by best individual rank, then by which ranking listed the item first.
    return sorted(scores.items(), key=lambda kv: (-kv[1], first_seen[kv[0]]))
