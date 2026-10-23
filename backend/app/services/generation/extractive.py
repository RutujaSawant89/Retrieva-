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
MIN_SENTENCE_SCORE = 0.2
RELATIVE_CUTOFF = 0.6


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

    lexical = np.array([c[0] for c in candidates], dtype=float)
    scores = lexical
    if embedder is not None:
        vectors = embedder.embed_documents([c[3] for c in candidates])
        semantic = np.clip(vectors @ embedder.embed_query(question), 0.0, 1.0)
        scores = 0.5 * lexical + 0.5 * semantic
    best = float(scores.max())
    if best < MIN_SENTENCE_SCORE:
        return None
    # Keep sentences close to the best one; evidence rank only breaks ties.
    cutoff = max(MIN_SENTENCE_SCORE, RELATIVE_CUTOFF * best)
    order = sorted(range(len(candidates)), key=lambda i: (-round(float(scores[i]), 3), candidates[i][1]))
    chosen: list[int] = []
    seen_words: list[set[str]] = []
    for idx in order:
        if scores[idx] < cutoff or len(chosen) >= MAX_SENTENCES:
            break
        if lexical[idx] == 0 and embedder is None:
            continue
        words = content_words(candidates[idx][3])
        if any(len(words & s) / max(1, len(words)) > 0.8 for s in seen_words):
            continue  # skip near-repeats
        chosen.append(idx)
        seen_words.append(words)
    if not chosen:
        return None
    chosen.sort(key=lambda i: (candidates[i][1], candidates[i][2]))
    return " ".join(f"{candidates[i][3].rstrip()} [{candidates[i][4]}]" for i in chosen)
