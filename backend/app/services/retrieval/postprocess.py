"""Post-retrieval processing: near-duplicate removal and contextual compression."""

from __future__ import annotations

import numpy as np

from app.services.retrieval.analyzer import analyze
from app.services.retrieval.types import Evidence
from app.services.text import split_sentences

DUPLICATE_JACCARD = 0.85


def _shingles(text: str, n: int = 3) -> set[tuple[str, ...]]:
    tokens = analyze(text, keep_stop_words=True)
    if len(tokens) < n:
        return {tuple(tokens)}
    return {tuple(tokens[i : i + n]) for i in range(len(tokens) - n + 1)}


def remove_near_duplicates(
    items: list[Evidence], threshold: float = DUPLICATE_JACCARD
) -> tuple[list[Evidence], int]:
    """Drop items whose text is (near-)identical to a higher-ranked item.

    Duplicates arise from re-uploaded content, overlapping chunks, and repeated boilerplate.
    """
    kept: list[Evidence] = []
    kept_shingles: list[set] = []
    seen_hashes: set[str] = set()
    removed = 0
    for item in items:
        if item.content_hash in seen_hashes:
            removed += 1
            continue
        shingles = _shingles(item.content)
        duplicate = False
        for other in kept_shingles:
            union = len(shingles | other)
            if union and len(shingles & other) / union >= threshold:
                duplicate = True
                break
        if duplicate:
            removed += 1
            continue
        kept.append(item)
        kept_shingles.append(shingles)
        seen_hashes.add(item.content_hash)
    return kept, removed


def compress(
    query: str,
    items: list[Evidence],
    sentence_vectors: callable | None = None,  # type: ignore[valid-type]
    query_vector: np.ndarray | None = None,
    keep_ratio: float = 0.5,
    min_sentences: int = 2,
) -> int:
    """Contextual compression: keep the sentences of each passage most related to the query.

    Sentences are scored by query-term overlap and, when vectors are available, embedding
    similarity. Kept sentences preserve their original order; the full chunk remains the
    citation target. Returns the number of characters removed.
    """
    query_terms = set(analyze(query))
    saved = 0
    for item in items:
        sentences = split_sentences(item.content)
        if len(sentences) <= min_sentences:
            continue
        lexical = np.array(
            [len(query_terms & set(analyze(s))) / max(1, len(query_terms)) for s in sentences], dtype=float
        )
        scores = lexical
        if sentence_vectors is not None and query_vector is not None:
            vectors = sentence_vectors(sentences)
            semantic = vectors @ query_vector
            scores = 0.5 * lexical + 0.5 * np.clip(semantic, 0, 1)
        keep_n = max(min_sentences, int(np.ceil(len(sentences) * keep_ratio)))
        keep = sorted(np.argsort(-scores)[:keep_n])
        compressed = " ".join(sentences[i] for i in keep)
        if len(compressed) < len(item.content):
            saved += len(item.content) - len(compressed)
            item.compressed = compressed
    return saved
