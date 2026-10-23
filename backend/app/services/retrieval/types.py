from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass, field
from typing import Literal

RetrievalStrategy = Literal["dense", "sparse", "hybrid"]
VectorMetric = Literal["cosine", "inner_product"]


@dataclass(frozen=True)
class RetrievalScope:
    """Who is searching and over which documents. Always derived from the authenticated user."""

    org_id: uuid.UUID
    user_id: uuid.UUID
    can_manage: bool = False
    # None means every document the user can see; otherwise an explicit allow-list.
    document_ids: tuple[uuid.UUID, ...] | None = None


@dataclass
class RetrievalConfig:
    strategy: RetrievalStrategy = "hybrid"
    top_k: int = 8
    candidate_k: int = 40
    rrf_k: int = 60
    dense_weight: float = 1.0
    sparse_weight: float = 1.0
    metric: VectorMetric = "cosine"
    rerank: bool = True
    # "auto" lets the query planner decide; True/False force the technique on/off.
    rewrite: bool | Literal["auto"] = "auto"
    multi_query: bool | Literal["auto"] = "auto"
    expansion: bool | Literal["auto"] = "auto"
    metadata_boost: bool = True
    compression: bool = False
    dedupe: bool = True
    relevance_threshold: float | None = None  # applied to the final-stage score

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Evidence:
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    document_title: str
    file_type: str
    content: str
    page_number: int | None
    page_end: int | None
    section: str | None
    heading_path: list[str]
    start_char: int
    end_char: int
    content_hash: str
    context_header: str = ""
    compressed: str | None = None
    # Stage scores. They are on different scales and must not be compared with each other.
    dense_score: float | None = None  # cosine similarity in [-1, 1]
    sparse_score: float | None = None  # raw BM25
    fusion_score: float | None = None  # RRF
    rerank_score: float | None = None  # cross-encoder logit (or lexical score)
    dense_rank: int | None = None
    sparse_rank: int | None = None
    final_rank: int = 0
    label: str = ""  # citation label, e.g. "S1", assigned during context assembly

    @property
    def text(self) -> str:
        return self.compressed or self.content

    @property
    def primary_score(self) -> float:
        for value in (self.rerank_score, self.fusion_score, self.dense_score, self.sparse_score):
            if value is not None:
                return value
        return 0.0

    def to_dict(self) -> dict:
        data = asdict(self)
        data["chunk_id"] = str(self.chunk_id)
        data["document_id"] = str(self.document_id)
        return data


@dataclass
class RetrievalResult:
    query: str
    normalized_query: str
    queries: list[str]
    evidence: list[Evidence]
    config: RetrievalConfig
    decisions: list[str] = field(default_factory=list)
    timings_ms: dict[str, float] = field(default_factory=dict)
    candidates_considered: int = 0
    reranker: str | None = None
    embedding_model: str | None = None

    @property
    def total_ms(self) -> float:
        return round(sum(self.timings_ms.values()), 1)
