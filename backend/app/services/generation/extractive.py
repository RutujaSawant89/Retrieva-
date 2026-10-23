"""Extractive answering: an LLM-free generation mode.

The answer is composed of verbatim sentences from the retrieved evidence that best match the
question, each cited with its source label. It cannot paraphrase or synthesise, but it cannot
hallucinate either, which makes it a useful offline baseline and a safe fallback.
"""

from __future__ import annotations

import numpy as np

from app.services.embeddings.service import EmbeddingService
from app.services.generation.context import AssembledContext
from app.services.retrieval.analyzer import content_words
from app.services.text import split_sentences

MAX_SENTENCES = 4
MIN_SENTENCE_SCORE = 0.25


def extractive_answer(
    question: str, context: AssembledContext, embedder: EmbeddingService | None
) -> str | None:
    """Return a cited answer, or ``None`` when no sentence is relevant enough."""
    query_terms = content_words(question)
    candidates: list[tuple[float, int, int, str, str]] = []  # score, item rank, position, sentence, label
    for rank, item in enumerate(context.items):
        for position, sentence in enumerate(split_sentences(item.text)):
            words = content_words(sentence)
            if len(words) < 3:
                continue
            lexical = len(query_terms & words) / max(1, len(query_terms))
            candidates.append((lexical, rank, position, sentence, item.label))
    if not candidates:
        return None

    scores = np.array([c[0] for c in candidates], dtype=float)
    if embedder is not None:
        vectors = embedder.embed_documents([c[3] for c in candidates])
        semantic = np.clip(vectors @ embedder.embed_query(question), 0.0, 1.0)
        scores = 0.5 * scores + 0.5 * semantic
    # Prefer sentences from higher-ranked evidence when scores are close.
    scores = scores - 0.02 * np.array([c[1] for c in candidates])

    order = np.argsort(-scores)
    chosen: list[int] = []
    seen_words: list[set[str]] = []
    for idx in order:
        if scores[idx] < MIN_SENTENCE_SCORE or len(chosen) >= MAX_SENTENCES:
            break
        words = content_words(candidates[idx][3])
        if any(len(words & s) / max(1, len(words)) > 0.8 for s in seen_words):
            continue  # skip near-repeats
        chosen.append(int(idx))
        seen_words.append(words)
    if not chosen:
        return None
    chosen.sort(key=lambda i: (candidates[i][1], candidates[i][2]))
    return " ".join(f"{candidates[i][3].rstrip()} [{candidates[i][4]}]" for i in chosen)
