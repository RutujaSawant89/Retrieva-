"""Embedding service: batching, retries, dimension validation, reuse and caching.

* Document vectors are reused from existing chunks with the same content hash and model
  version in the same organization, so re-uploading or re-processing unchanged text does not
  recompute embeddings.
* Query vectors are cached in-process (LRU) and in Redis when available.
"""

from __future__ import annotations

import hashlib
import logging
import time
import uuid
from collections import OrderedDict
from threading import Lock

import numpy as np
import redis
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.metrics import CACHE_EVENTS, EMBEDDING_LATENCY
from app.core.redis import get_redis
from app.db.models import DocumentChunk
from app.services.embeddings.providers import EmbeddingProvider, get_embedding_provider

logger = logging.getLogger(__name__)

MAX_ATTEMPTS = 3
QUERY_CACHE_SIZE = 2048
QUERY_CACHE_TTL_SECONDS = 24 * 3600


class EmbeddingError(Exception):
    pass


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class EmbeddingService:
    def __init__(self, provider: EmbeddingProvider | None = None) -> None:
        self.provider = provider or get_embedding_provider()
        self._query_cache: OrderedDict[str, np.ndarray] = OrderedDict()
        self._lock = Lock()

    @property
    def model_version(self) -> str:
        return self.provider.version

    def _validate(self, vectors: np.ndarray, expected_rows: int) -> np.ndarray:
        if vectors.ndim != 2 or vectors.shape[0] != expected_rows:
            raise EmbeddingError(f"Provider returned shape {vectors.shape}, expected ({expected_rows}, d)")
        if vectors.shape[1] != self.provider.dimension:
            raise EmbeddingError(
                f"Embedding dimension {vectors.shape[1]} does not match configured {self.provider.dimension}"
            )
        if not np.all(np.isfinite(vectors)):
            raise EmbeddingError("Provider returned non-finite values")
        return vectors

    def embed_documents(self, texts: list[str], batch_size: int = 64) -> np.ndarray:
        """Embed texts in batches with retry; raises ``EmbeddingError`` after repeated failure."""
        if not texts:
            return np.zeros((0, self.provider.dimension), np.float32)
        out: list[np.ndarray] = []
        for start in range(0, len(texts), batch_size):
            batch = texts[start : start + batch_size]
            for attempt in range(1, MAX_ATTEMPTS + 1):
                began = time.perf_counter()
                try:
                    vectors = self._validate(self.provider.embed_documents(batch), len(batch))
                    EMBEDDING_LATENCY.labels(self.provider.name, "documents").observe(
                        time.perf_counter() - began
                    )
                    out.append(vectors)
                    break
                except EmbeddingError:
                    raise
                except Exception as exc:
                    if attempt == MAX_ATTEMPTS:
                        raise EmbeddingError(
                            f"Embedding failed after {MAX_ATTEMPTS} attempts: {exc}"
                        ) from exc
                    logger.warning("embedding_retry", extra={"attempt": attempt, "error": str(exc)})
                    time.sleep(0.5 * attempt)
        return np.vstack(out)

    def embed_documents_with_reuse(
        self, db: Session, org_id: uuid.UUID, texts: list[str], hashes: list[str]
    ) -> tuple[np.ndarray, int]:
        """Return vectors for ``texts``, reusing stored vectors for identical content.

        Returns ``(vectors, reused_count)``.
        """
        existing: dict[str, np.ndarray] = {}
        unique_hashes = list(set(hashes))
        for start in range(0, len(unique_hashes), 500):
            rows = db.execute(
                select(DocumentChunk.content_hash, DocumentChunk.embedding)
                .where(
                    DocumentChunk.organization_id == org_id,
                    DocumentChunk.embedding_model == self.model_version,
                    DocumentChunk.content_hash.in_(unique_hashes[start : start + 500]),
                    DocumentChunk.embedding.is_not(None),
                )
                .distinct(DocumentChunk.content_hash)
            ).all()
            for h, vector in rows:
                existing[h] = np.asarray(vector, dtype=np.float32)

        missing_idx = [i for i, h in enumerate(hashes) if h not in existing]
        computed = self.embed_documents([texts[i] for i in missing_idx]) if missing_idx else None
        vectors = np.zeros((len(texts), self.provider.dimension), np.float32)
        for i, h in enumerate(hashes):
            if h in existing:
                vectors[i] = existing[h]
        if computed is not None:
            for row, i in enumerate(missing_idx):
                vectors[i] = computed[row]
        reused = len(texts) - len(missing_idx)
        CACHE_EVENTS.labels("embedding_reuse", "hit").inc(reused)
        CACHE_EVENTS.labels("embedding_reuse", "miss").inc(len(missing_idx))
        return vectors, reused

    def embed_query(self, text: str) -> np.ndarray:
        key = f"emb:q:{self.model_version}:{content_hash(text)}"
        with self._lock:
            cached = self._query_cache.get(key)
            if cached is not None:
                self._query_cache.move_to_end(key)
                CACHE_EVENTS.labels("query_embedding", "hit").inc()
                return cached
        client = get_redis()
        if client is not None:
            try:
                raw = client.get(key)
                if raw:
                    vector = np.frombuffer(raw, dtype=np.float32).copy()
                    if vector.shape[0] == self.provider.dimension:
                        CACHE_EVENTS.labels("query_embedding", "hit").inc()
                        self._remember(key, vector)
                        return vector
            except redis.RedisError:
                logger.debug("redis_query_cache_read_failed")
        CACHE_EVENTS.labels("query_embedding", "miss").inc()
        began = time.perf_counter()
        vector = np.asarray(self.provider.embed_query(text), dtype=np.float32)
        EMBEDDING_LATENCY.labels(self.provider.name, "query").observe(time.perf_counter() - began)
        if vector.shape != (self.provider.dimension,):
            raise EmbeddingError(f"Query embedding has shape {vector.shape}")
        self._remember(key, vector)
        if client is not None:
            try:
                client.setex(key, QUERY_CACHE_TTL_SECONDS, vector.tobytes())
            except redis.RedisError:
                logger.debug("redis_query_cache_write_failed")
        return vector

    def _remember(self, key: str, vector: np.ndarray) -> None:
        with self._lock:
            self._query_cache[key] = vector
            self._query_cache.move_to_end(key)
            while len(self._query_cache) > QUERY_CACHE_SIZE:
                self._query_cache.popitem(last=False)


_service: EmbeddingService | None = None
_service_lock = Lock()


def get_embedding_service() -> EmbeddingService:
    global _service
    if _service is None:
        with _service_lock:
            if _service is None:
                _service = EmbeddingService()
    return _service
