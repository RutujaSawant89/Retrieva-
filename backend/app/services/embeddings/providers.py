"""Embedding providers.

* ``SentenceTransformerProvider`` — production provider (e.g. ``BAAI/bge-small-en-v1.5``).
* ``HashingProvider`` — deterministic feature-hashing of unigrams and bigrams. It captures
  lexical overlap only (no semantics) and exists so tests and CI run quickly and offline.
  It is never selected implicitly: ``EMBEDDING_PROVIDER=hashing`` must be set.
"""

from __future__ import annotations

import hashlib
import logging
import re
import threading
from abc import ABC, abstractmethod
from functools import lru_cache

import numpy as np

from app.core.config import get_settings
from app.services.text import approx_token_count

logger = logging.getLogger(__name__)


class EmbeddingProvider(ABC):
    name: str
    dimension: int

    @property
    def version(self) -> str:
        """Identifier stored with every vector so vectors from different models never mix."""
        return self.name

    @abstractmethod
    def embed_documents(self, texts: list[str]) -> np.ndarray: ...

    @abstractmethod
    def embed_query(self, text: str) -> np.ndarray: ...

    def count_tokens(self, text: str) -> int:
        return approx_token_count(text)


class HashingProvider(EmbeddingProvider):
    _TOKEN = re.compile(r"[a-z0-9]+")

    def __init__(self, dimension: int, name: str = "hashing-v1") -> None:
        self.dimension = dimension
        self.name = name

    def _vector(self, text: str) -> np.ndarray:
        tokens = self._TOKEN.findall(text.lower())
        features = tokens + [f"{a}_{b}" for a, b in zip(tokens, tokens[1:], strict=False)]
        vec = np.zeros(self.dimension, dtype=np.float32)
        for feature in features:
            digest = hashlib.blake2b(feature.encode(), digest_size=8).digest()
            bucket = int.from_bytes(digest[:4], "little") % self.dimension
            sign = 1.0 if digest[4] & 1 else -1.0
            vec[bucket] += sign
        norm = float(np.linalg.norm(vec))
        return vec / norm if norm else vec

    def embed_documents(self, texts: list[str]) -> np.ndarray:
        return (
            np.vstack([self._vector(t) for t in texts])
            if texts
            else np.zeros((0, self.dimension), np.float32)
        )

    def embed_query(self, text: str) -> np.ndarray:
        return self._vector(text)


class SentenceTransformerProvider(EmbeddingProvider):
    def __init__(self, model_name: str, dimension: int, query_prefix: str = "", batch_size: int = 32) -> None:
        self.name = model_name
        self.dimension = dimension
        self.query_prefix = query_prefix
        self.batch_size = batch_size
        self._model = None
        self._lock = threading.Lock()

    @property
    def model(self):  # type: ignore[no-untyped-def]
        if self._model is None:
            with self._lock:
                if self._model is None:
                    from sentence_transformers import SentenceTransformer

                    logger.info("loading_embedding_model", extra={"model": self.name})
                    model = SentenceTransformer(self.name, device="cpu")
                    dimension_of = (
                        getattr(model, "get_embedding_dimension", None)
                        or model.get_sentence_embedding_dimension
                    )
                    actual = dimension_of()
                    if actual != self.dimension:
                        raise ValueError(
                            f"Embedding model {self.name} produces {actual}-d vectors but EMBEDDING_DIM="
                            f"{self.dimension}; update EMBEDDING_DIM and add a migration"
                        )
                    self._model = model
        return self._model

    def embed_documents(self, texts: list[str]) -> np.ndarray:
        if not texts:
            return np.zeros((0, self.dimension), np.float32)
        vectors = self.model.encode(
            texts, batch_size=self.batch_size, normalize_embeddings=True, show_progress_bar=False
        )
        return np.asarray(vectors, dtype=np.float32)

    def embed_query(self, text: str) -> np.ndarray:
        vector = self.model.encode(
            [self.query_prefix + text], normalize_embeddings=True, show_progress_bar=False
        )[0]
        return np.asarray(vector, dtype=np.float32)

    def count_tokens(self, text: str) -> int:
        tokenizer = getattr(self.model, "tokenizer", None)
        if tokenizer is None:
            return approx_token_count(text)
        return len(tokenizer.encode(text, add_special_tokens=False, truncation=False))


def configure_model_hub() -> None:
    """Apply Hugging Face Hub settings before any model is loaded."""
    import os

    if get_settings().hf_offline:
        os.environ.setdefault("HF_HUB_OFFLINE", "1")
        os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
    os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")


@lru_cache
def get_embedding_provider() -> EmbeddingProvider:
    configure_model_hub()
    settings = get_settings()
    if settings.embedding_provider == "hashing":
        return HashingProvider(settings.embedding_dim, name=settings.embedding_model or "hashing-v1")
    return SentenceTransformerProvider(
        settings.embedding_model,
        settings.embedding_dim,
        query_prefix=settings.embedding_query_prefix if "bge" in settings.embedding_model.lower() else "",
        batch_size=settings.embedding_batch_size,
    )
