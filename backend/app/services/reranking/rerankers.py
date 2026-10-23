"""Rerankers re-score (query, passage) pairs jointly.

* ``CrossEncoderReranker`` — e.g. ``cross-encoder/ms-marco-MiniLM-L-6-v2``; outputs relevance
  logits (higher is more relevant, roughly > 0 relevant, < -5 irrelevant for MS MARCO models).
* ``LexicalReranker`` — query-term coverage plus BM25 over the candidate set. Offline and
  deterministic; used in tests and as a fallback when no model is available.
"""

from __future__ import annotations

import logging
import threading
import time
from abc import ABC, abstractmethod
from functools import lru_cache

from app.core.config import get_settings
from app.core.metrics import RETRIEVAL_LATENCY
from app.services.retrieval.analyzer import analyze
from app.services.retrieval.bm25 import BM25Index

logger = logging.getLogger(__name__)


class Reranker(ABC):
    name: str

    @abstractmethod
    def score(self, query: str, passages: list[str]) -> list[float]: ...

    def rerank(self, query: str, passages: list[str]) -> list[float]:
        began = time.perf_counter()
        scores = self.score(query, passages) if passages else []
        RETRIEVAL_LATENCY.labels("rerank").observe(time.perf_counter() - began)
        return scores


class CrossEncoderReranker(Reranker):
    def __init__(self, model_name: str, batch_size: int = 16, max_length: int = 512) -> None:
        self.name = model_name
        self.batch_size = batch_size
        self.max_length = max_length
        self._model = None
        self._lock = threading.Lock()

    @property
    def model(self):  # type: ignore[no-untyped-def]
        if self._model is None:
            with self._lock:
                if self._model is None:
                    from app.services.embeddings.providers import configure_model_hub

                    configure_model_hub()  # must precede the first huggingface_hub import
                    from sentence_transformers import CrossEncoder

                    logger.info("loading_cross_encoder", extra={"model": self.name})
                    self._model = CrossEncoder(self.name, max_length=self.max_length, device="cpu")
        return self._model

    def score(self, query: str, passages: list[str]) -> list[float]:
        pairs = [(query, passage) for passage in passages]
        scores = self.model.predict(pairs, batch_size=self.batch_size, show_progress_bar=False)
        return [float(s) for s in scores]


class LexicalReranker(Reranker):
    name = "lexical-v1"

    def score(self, query: str, passages: list[str]) -> list[float]:
        query_terms = set(analyze(query))
        if not query_terms:
            return [0.0] * len(passages)
        local = BM25Index(list(range(len(passages))), passages)
        bm25 = local.scores(dict.fromkeys(query_terms, 1.0))
        top = float(bm25.max()) or 1.0
        out = []
        for i, passage in enumerate(passages):
            terms = set(analyze(passage))
            coverage = len(query_terms & terms) / len(query_terms)
            out.append(round(2.0 * coverage + float(bm25[i]) / top, 6))
        return out


@lru_cache
def get_reranker() -> Reranker | None:
    settings = get_settings()
    if settings.reranker_provider == "none":
        return None
    if settings.reranker_provider == "lexical":
        return LexicalReranker()
    return CrossEncoderReranker(settings.reranker_model)
