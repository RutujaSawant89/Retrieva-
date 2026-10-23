from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, Form, Query, Request, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from app.api.deps import CurrentUser, DbSession, client_ip, require
from app.core.config import get_settings
from app.core.errors import NotFoundError, ValidationFailedError
from app.core.permissions import Permission
from app.db.models import EvaluationDataset, EvaluationResult, EvaluationRun, RunStatus
from app.schemas.chat import RetrievalOptions
from app.schemas.common import Message, Page
from app.services import access, audit
from app.services.embeddings.service import get_embedding_service
from app.services.evaluation.datasets import normalize_items, parse_dataset_file
from app.services.generation.providers import get_llm
from app.services.ingestion.dispatch import dispatch_evaluation
from app.services.reranking.rerankers import get_reranker

router = APIRouter(prefix="/evaluation", tags=["evaluation"])

Reader = Annotated[CurrentUser, Depends(require(Permission.EVALUATION_READ))]
Runner = Annotated[CurrentUser, Depends(require(Permission.EVALUATION_RUN))]

MAX_EXPERIMENTS = 8

# Standard comparisons. Each entry is a set of named retrieval configurations.
PRESETS: dict[str, dict[str, Any]] = {
    "retrieval_strategies": {
        "label": "BM25 vs dense vs hybrid vs hybrid + rerank",
        "experiments": [
            {"name": "BM25", "options": {"strategy": "sparse", "rerank": False}},
            {"name": "Dense", "options": {"strategy": "dense", "rerank": False}},
            {"name": "Hybrid (RRF)", "options": {"strategy": "hybrid", "rerank": False}},
            {"name": "Hybrid + rerank", "options": {"strategy": "hybrid", "rerank": True}},
        ],
    },
    "fusion_weights": {
        "label": "RRF weighting: dense-heavy vs balanced vs BM25-heavy",
        "experiments": [
            {
                "name": "Dense ×2",
                "options": {"strategy": "hybrid", "dense_weight": 2.0, "sparse_weight": 1.0, "rerank": False},
            },
            {"name": "Balanced", "options": {"strategy": "hybrid", "rerank": False}},
            {
                "name": "BM25 ×2",
                "options": {"strategy": "hybrid", "dense_weight": 1.0, "sparse_weight": 2.0, "rerank": False},
            },
        ],
    },
    "query_techniques": {
        "label": "Query expansion and multi-query on vs off",
        "experiments": [
            {
                "name": "Plain",
                "options": {"strategy": "hybrid", "expansion": False, "multi_query": False, "rerank": True},
            },
            {
                "name": "+ BM25 expansion",
                "options": {"strategy": "hybrid", "expansion": True, "multi_query": False, "rerank": True},
            },
            {
                "name": "+ Multi-query",
                "options": {"strategy": "hybrid", "expansion": False, "multi_query": True, "rerank": True},
            },
        ],
    },
    "top_k": {
        "label": "Candidate pool size before reranking",
        "experiments": [
            {"name": "Candidates 10", "options": {"strategy": "hybrid", "candidate_k": 10, "rerank": True}},
            {"name": "Candidates 40", "options": {"strategy": "hybrid", "candidate_k": 40, "rerank": True}},
            {"name": "Candidates 100", "options": {"strategy": "hybrid", "candidate_k": 100, "rerank": True}},
        ],
    },
}


class DatasetCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=2000)
    items: list[dict[str, Any]]


class DatasetOut(BaseModel):
    id: uuid.UUID
    name: str
    version: int
    description: str
    item_count: int
    created_at: datetime


class DatasetDetail(DatasetOut):
    items: list[dict[str, Any]]


class Experiment(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    options: RetrievalOptions = Field(default_factory=RetrievalOptions)


class RunRequest(BaseModel):
    dataset_id: uuid.UUID
    name: str = Field(default="Experiment", min_length=1, max_length=150)
    experiments: list[Experiment] | None = None
    preset: str | None = None
    ks: list[int] = Field(default_factory=lambda: [1, 3, 5, 10])
    generate: bool = False
    use_ragas: bool = False
    document_ids: list[uuid.UUID] = Field(default_factory=list, max_length=200)


class RunOut(BaseModel):
    id: uuid.UUID
    dataset_id: uuid.UUID
    dataset_version: int
    name: str
    status: str
    config: dict[str, Any]
    embedding_model: str
    reranker_model: str | None
    llm_provider: str | None
    llm_model: str | None
    metrics: dict[str, Any]
    error_message: str | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


def _dataset_out(d: EvaluationDataset) -> DatasetOut:
    return DatasetOut(
        id=d.id,
        name=d.name,
        version=d.version,
        description=d.description,
        item_count=d.item_count,
        created_at=d.created_at,
    )


def _run_out(r: EvaluationRun) -> RunOut:
    return RunOut(
        id=r.id,
        dataset_id=r.dataset_id,
        dataset_version=r.dataset_version,
        name=r.name,
        status=r.status.value,
        config=r.config,
        embedding_model=r.embedding_model,
        reranker_model=r.reranker_model,
        llm_provider=r.llm_provider,
        llm_model=r.llm_model,
        metrics=r.metrics,
        error_message=r.error_message,
        created_at=r.created_at,
        started_at=r.started_at,
        finished_at=r.finished_at,
    )


def _create_dataset(
    db: DbSession, current: CurrentUser, name: str, description: str, items: list[dict]
) -> EvaluationDataset:
    latest = db.scalar(
        select(func.max(EvaluationDataset.version)).where(
            EvaluationDataset.organization_id == current.org_id, EvaluationDataset.name == name
        )
    )
    dataset = EvaluationDataset(
        organization_id=current.org_id,
        name=name,
        version=(latest or 0) + 1,
        description=description,
        items=items,
        item_count=len(items),
        created_by=current.id,
    )
    db.add(dataset)
    db.flush()
    return dataset


@router.get("/presets")
def presets(_: Reader) -> dict[str, Any]:
    return PRESETS


@router.post("/datasets", response_model=DatasetOut, status_code=status.HTTP_201_CREATED)
def create_dataset(body: DatasetCreate, current: Runner, db: DbSession) -> DatasetOut:
    return _dataset_out(
        _create_dataset(db, current, body.name.strip(), body.description, normalize_items(body.items))
    )


@router.post("/datasets/upload", response_model=DatasetOut, status_code=status.HTTP_201_CREATED)
def upload_dataset(
    current: Runner,
    db: DbSession,
    file: Annotated[UploadFile, File()],
    name: Annotated[str, Form(min_length=1, max_length=200)],
    description: Annotated[str, Form(max_length=2000)] = "",
) -> DatasetOut:
    data = file.file.read(5 * 1024 * 1024 + 1)
    if len(data) > 5 * 1024 * 1024:
        raise ValidationFailedError("Dataset files are limited to 5 MB")
    items = parse_dataset_file(file.filename or "dataset.json", data)
    return _dataset_out(_create_dataset(db, current, name.strip(), description, items))


@router.get("/datasets", response_model=Page[DatasetOut])
def list_datasets(
    current: Reader, db: DbSession, page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=100)
) -> Page[DatasetOut]:
    stmt = select(EvaluationDataset).where(EvaluationDataset.organization_id == current.org_id)
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(
        stmt.order_by(EvaluationDataset.name, EvaluationDataset.version.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return Page(items=[_dataset_out(d) for d in rows], total=total, page=page, page_size=page_size)


def _dataset(db: DbSession, current: CurrentUser, dataset_id: uuid.UUID) -> EvaluationDataset:
    dataset = db.scalar(
        select(EvaluationDataset).where(
            EvaluationDataset.id == dataset_id, EvaluationDataset.organization_id == current.org_id
        )
    )
    if dataset is None:
        raise NotFoundError("Dataset not found")
    return dataset


@router.get("/datasets/{dataset_id}", response_model=DatasetDetail)
def get_dataset(dataset_id: uuid.UUID, current: Reader, db: DbSession) -> DatasetDetail:
    d = _dataset(db, current, dataset_id)
    return DatasetDetail(**_dataset_out(d).model_dump(), items=d.items)


@router.delete("/datasets/{dataset_id}", response_model=Message)
def delete_dataset(dataset_id: uuid.UUID, current: Runner, request: Request, db: DbSession) -> Message:
    d = _dataset(db, current, dataset_id)
    db.delete(d)  # runs and results cascade
    audit.record(
        db,
        org_id=current.org_id,
        user_id=current.id,
        action="evaluation.dataset_deleted",
        resource_type="dataset",
        resource_id=dataset_id,
        ip_address=client_ip(request),
    )
    return Message(message="Dataset and its runs deleted")


@router.post("/run", response_model=list[RunOut], status_code=status.HTTP_202_ACCEPTED)
def start_run(body: RunRequest, current: Runner, request: Request, db: DbSession) -> list[RunOut]:
    dataset = _dataset(db, current, body.dataset_id)
    if body.preset:
        if body.preset not in PRESETS:
            raise ValidationFailedError(f"Unknown preset '{body.preset}'")
        experiments = [Experiment.model_validate(e) for e in PRESETS[body.preset]["experiments"]]
    else:
        experiments = body.experiments or [Experiment(name=body.name)]
    if len(experiments) > MAX_EXPERIMENTS:
        raise ValidationFailedError(f"At most {MAX_EXPERIMENTS} configurations per request")
    ks = sorted({k for k in body.ks if 1 <= k <= 50}) or [1, 3, 5, 10]
    if body.document_ids:
        access.resolve_scope_document_ids(db, current, body.document_ids, None)

    settings = get_settings()
    llm = get_llm() if body.generate else None
    reranker = get_reranker()
    runs: list[EvaluationRun] = []
    for experiment in experiments:
        run = EvaluationRun(
            organization_id=current.org_id,
            dataset_id=dataset.id,
            dataset_version=dataset.version,
            name=f"{body.name} · {experiment.name}" if len(experiments) > 1 else experiment.name,
            status=RunStatus.PENDING,
            config={
                "experiment": experiment.name,
                "group": body.name,
                "retrieval": experiment.options.model_dump(),
                "ks": ks,
                "generate": body.generate,
                "use_ragas": body.use_ragas,
                "document_ids": [str(d) for d in body.document_ids],
                "chunking": {
                    "strategy": settings.chunking_strategy,
                    "chunk_size": settings.chunk_size,
                    "chunk_overlap": settings.chunk_overlap,
                },
            },
            embedding_model=get_embedding_service().model_version,
            reranker_model=reranker.name if reranker and experiment.options.rerank else None,
            llm_provider=(llm.name if llm else "extractive") if body.generate else None,
            llm_model=(llm.model if llm else "extractive-v1") if body.generate else None,
            created_by=current.id,
        )
        db.add(run)
        runs.append(run)
    db.flush()
    audit.record(
        db,
        org_id=current.org_id,
        user_id=current.id,
        action="evaluation.started",
        resource_type="dataset",
        resource_id=dataset.id,
        ip_address=client_ip(request),
        details={"runs": len(runs), "preset": body.preset},
    )
    db.commit()
    for run in runs:
        dispatch_evaluation(run.id, current.org_id)
    db.expire_all()
    return [_run_out(db.get(EvaluationRun, r.id)) for r in runs]  # type: ignore[arg-type]


@router.get("/runs", response_model=Page[RunOut])
def list_runs(
    current: Reader,
    db: DbSession,
    dataset_id: uuid.UUID | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
) -> Page[RunOut]:
    stmt = select(EvaluationRun).where(EvaluationRun.organization_id == current.org_id)
    if dataset_id:
        stmt = stmt.where(EvaluationRun.dataset_id == dataset_id)
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(
        stmt.order_by(EvaluationRun.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    )
    return Page(items=[_run_out(r) for r in rows], total=total, page=page, page_size=page_size)


@router.get("/runs/{run_id}")
def get_run(run_id: uuid.UUID, current: Reader, db: DbSession) -> dict[str, Any]:
    run = db.scalar(
        select(EvaluationRun).where(
            EvaluationRun.id == run_id, EvaluationRun.organization_id == current.org_id
        )
    )
    if run is None:
        raise NotFoundError("Evaluation run not found")
    results = db.scalars(
        select(EvaluationResult)
        .where(EvaluationResult.run_id == run.id)
        .order_by(EvaluationResult.item_index)
    ).all()
    return {
        **_run_out(run).model_dump(mode="json"),
        "results": [
            {
                "item_index": r.item_index,
                "question": r.question,
                "answer": r.answer,
                "metrics": r.metrics,
                "retrieved": r.retrieved,
                "latency_ms": r.latency_ms,
            }
            for r in results
        ],
    }


@router.delete("/runs/{run_id}", response_model=Message)
def delete_run(run_id: uuid.UUID, current: Runner, db: DbSession) -> Message:
    run = db.scalar(
        select(EvaluationRun).where(
            EvaluationRun.id == run_id, EvaluationRun.organization_id == current.org_id
        )
    )
    if run is None:
        raise NotFoundError("Evaluation run not found")
    db.delete(run)
    return Message(message="Run deleted")
