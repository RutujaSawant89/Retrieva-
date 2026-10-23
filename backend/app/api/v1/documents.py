from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, File, Form, Query, Request, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import delete, func, or_, select
from sqlalchemy.exc import IntegrityError

from app.api.deps import AuthUser, CurrentUser, DbSession, client_ip, require
from app.core.errors import AppError, NotFoundError, ValidationFailedError
from app.core.permissions import Permission
from app.db.models import (
    CollectionDocument,
    Document,
    DocumentChunk,
    DocumentStatus,
    IngestionJob,
    User,
    Visibility,
)
from app.schemas.common import Message, Page
from app.schemas.documents import (
    ChunkOut,
    DocumentContent,
    DocumentDetail,
    DocumentOut,
    DocumentStatusOut,
    DocumentUpdate,
    IngestionJobOut,
    ReprocessRequest,
    UploadResponse,
    UploadResult,
    VisibilityLiteral,
)
from app.services import access, audit, storage
from app.services.ingestion.dispatch import dispatch_ingestion

router = APIRouter(prefix="/documents", tags=["documents"])

Writer = Annotated[CurrentUser, Depends(require(Permission.DOCUMENTS_WRITE))]
MAX_FILES_PER_REQUEST = 20


def _title_from_filename(filename: str) -> str:
    stem = Path(filename).stem.replace("_", " ").replace("-", " ").strip()
    return " ".join(stem.split())[:500] or filename[:500]


def _to_out(
    document: Document, owner_name: str | None = None, collection_ids: list[uuid.UUID] | None = None
) -> DocumentOut:
    out = DocumentOut.model_validate(document)
    out.owner_name = owner_name
    out.collection_ids = collection_ids or []
    return out


def _collections_for(db: DbSession, ids: list[uuid.UUID]) -> dict[uuid.UUID, list[uuid.UUID]]:
    mapping: dict[uuid.UUID, list[uuid.UUID]] = {i: [] for i in ids}
    if ids:
        for doc_id, coll_id in db.execute(
            select(CollectionDocument.document_id, CollectionDocument.collection_id).where(
                CollectionDocument.document_id.in_(ids)
            )
        ):
            mapping[doc_id].append(coll_id)
    return mapping


@router.post("/upload", response_model=UploadResponse, status_code=status.HTTP_201_CREATED)
def upload_documents(
    current: Writer,
    request: Request,
    db: DbSession,
    files: Annotated[list[UploadFile], File(description="One or more documents")],
    category: Annotated[str | None, Form(max_length=100)] = None,
    visibility: Annotated[VisibilityLiteral, Form()] = "organization",
    collection_id: Annotated[uuid.UUID | None, Form()] = None,
) -> UploadResponse:
    if not files:
        raise ValidationFailedError("No files were provided")
    if len(files) > MAX_FILES_PER_REQUEST:
        raise ValidationFailedError(f"At most {MAX_FILES_PER_REQUEST} files per upload")
    collection = None
    if collection_id is not None:
        collection = access.get_collection(db, current, collection_id)
        access.ensure_can_modify_collection(current, collection)

    results: list[UploadResult] = []
    to_dispatch: list[tuple[uuid.UUID, uuid.UUID]] = []
    for upload in files:
        filename = storage.safe_display_name(upload.filename or "untitled")
        document_id = uuid.uuid4()
        try:
            stored = storage.store_upload(upload.file, current.org_id, document_id, filename)
        except AppError as exc:
            results.append(UploadResult(filename=filename, outcome="rejected", error=exc.message))
            continue

        existing = db.scalar(
            select(Document).where(
                Document.organization_id == current.org_id,
                Document.content_hash == stored.sha256,
                Document.deleted_at.is_(None),
            )
        )
        if existing is not None:
            stored.path.unlink(missing_ok=True)
            visible = db.scalar(
                select(Document.id).where(
                    Document.id == existing.id, access.document_visibility_clause(current)
                )
            )
            results.append(
                UploadResult(
                    filename=filename,
                    outcome="duplicate",
                    duplicate_of=existing.id if visible else None,
                    error="An identical document already exists in this organization",
                )
            )
            continue

        document = Document(
            id=document_id,
            organization_id=current.org_id,
            owner_id=current.id,
            title=_title_from_filename(filename),
            original_filename=filename,
            file_type=stored.file_type,
            mime_type=stored.mime_type,
            file_size=stored.size,
            content_hash=stored.sha256,
            storage_path=storage.relative(stored.path),
            category=(category or "").strip() or None,
            visibility=Visibility(visibility),
            status=DocumentStatus.QUEUED,
            doc_metadata={},
        )
        job = IngestionJob(
            organization_id=current.org_id, document_id=document_id, status=DocumentStatus.QUEUED, config={}
        )
        savepoint = db.begin_nested()
        try:
            db.add(document)
            db.flush()
            db.add(job)
            if collection is not None:
                db.add(
                    CollectionDocument(
                        collection_id=collection.id,
                        document_id=document_id,
                        organization_id=current.org_id,
                        added_by=current.id,
                    )
                )
            db.flush()
            savepoint.commit()
        except IntegrityError:
            savepoint.rollback()
            stored.path.unlink(missing_ok=True)
            results.append(
                UploadResult(
                    filename=filename,
                    outcome="duplicate",
                    error="An identical document was uploaded concurrently",
                )
            )
            continue
        audit.record(
            db,
            org_id=current.org_id,
            user_id=current.id,
            action="document.uploaded",
            resource_type="document",
            resource_id=document_id,
            ip_address=client_ip(request),
            details={"filename": filename, "size": stored.size, "sha256": stored.sha256},
        )
        results.append(
            UploadResult(
                filename=filename,
                outcome="created",
                document=_to_out(document, current.user.full_name, [collection.id] if collection else []),
            )
        )
        to_dispatch.append((document_id, job.id))

    db.commit()  # documents must be visible to the worker before it starts
    for document_id, job_id in to_dispatch:
        task_id = dispatch_ingestion(document_id, current.org_id, job_id)
        if task_id:
            db.execute(
                IngestionJob.__table__.update().where(IngestionJob.id == job_id).values(task_id=task_id)
            )
    if to_dispatch:
        db.commit()
        db.expire_all()
        # Inline mode finishes during the request: return fresh statuses.
        fresh = {
            d.id: d for d in db.scalars(select(Document).where(Document.id.in_([d for d, _ in to_dispatch])))
        }
        for result in results:
            if result.document and result.document.id in fresh:
                result.document = _to_out(
                    fresh[result.document.id], result.document.owner_name, result.document.collection_ids
                )
    return UploadResponse(results=results)


SortField = Literal["created_at", "title", "file_size", "status"]


@router.get("", response_model=Page[DocumentOut])
def list_documents(
    current: Annotated[CurrentUser, Depends(require(Permission.DOCUMENTS_READ))],
    db: DbSession,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    q: str | None = Query(None, max_length=200),
    status_filter: Annotated[list[str] | None, Query(alias="status")] = None,
    file_type: str | None = Query(None, max_length=16),
    category: str | None = Query(None, max_length=100),
    collection_id: uuid.UUID | None = None,
    mine: bool = False,
    sort: SortField = "created_at",
    order: Literal["asc", "desc"] = "desc",
) -> Page[DocumentOut]:
    stmt = (
        select(Document, User.full_name)
        .outerjoin(User, User.id == Document.owner_id)
        .where(access.document_visibility_clause(current))
    )
    if q:
        like = f"%{q.lower()}%"
        stmt = stmt.where(
            or_(func.lower(Document.title).like(like), func.lower(Document.original_filename).like(like))
        )
    if status_filter:
        valid = [s for s in status_filter if s in DocumentStatus._value2member_map_]
        stmt = stmt.where(Document.status.in_([DocumentStatus(s) for s in valid]))
    if file_type:
        stmt = stmt.where(Document.file_type == file_type)
    if category:
        stmt = stmt.where(Document.category == category)
    if mine:
        stmt = stmt.where(Document.owner_id == current.id)
    if collection_id:
        access.get_collection(db, current, collection_id)
        stmt = stmt.join(CollectionDocument, CollectionDocument.document_id == Document.id).where(
            CollectionDocument.collection_id == collection_id
        )
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    column = getattr(Document, sort)
    stmt = stmt.order_by(column.asc() if order == "asc" else column.desc(), Document.id)
    rows = db.execute(stmt.offset((page - 1) * page_size).limit(page_size)).all()
    collections = _collections_for(db, [d.id for d, _ in rows])
    items = [_to_out(d, owner, collections.get(d.id)) for d, owner in rows]
    return Page(items=items, total=total, page=page, page_size=page_size)


@router.get("/categories", response_model=list[str])
def list_categories(
    current: Annotated[CurrentUser, Depends(require(Permission.DOCUMENTS_READ))], db: DbSession
) -> list[str]:
    return list(
        db.scalars(
            select(Document.category)
            .where(access.document_visibility_clause(current), Document.category.is_not(None))
            .distinct()
            .order_by(Document.category)
        )
    )


@router.get("/{document_id}", response_model=DocumentDetail)
def get_document(document_id: uuid.UUID, current: AuthUser, db: DbSession) -> DocumentDetail:
    document = access.get_document(db, current, document_id)
    owner = (
        db.scalar(select(User.full_name).where(User.id == document.owner_id)) if document.owner_id else None
    )
    job = db.scalar(
        select(IngestionJob)
        .where(IngestionJob.document_id == document.id)
        .order_by(IngestionJob.created_at.desc())
        .limit(1)
    )
    base = _to_out(document, owner, _collections_for(db, [document.id]).get(document.id))
    try:
        access.ensure_can_modify(current, document)
        can_modify = True
    except AppError:
        can_modify = False
    return DocumentDetail(
        **base.model_dump(),
        metadata=document.doc_metadata or {},
        latest_job=IngestionJobOut.model_validate(job) if job else None,
        can_modify=can_modify,
    )


@router.get("/{document_id}/status", response_model=DocumentStatusOut)
def document_status(document_id: uuid.UUID, current: AuthUser, db: DbSession) -> DocumentStatusOut:
    document = access.get_document(db, current, document_id)
    return DocumentStatusOut(
        id=document.id,
        status=document.status.value,
        progress=document.progress,
        error_message=document.error_message,
        chunk_count=document.chunk_count,
    )


@router.patch("/{document_id}", response_model=DocumentOut)
def update_document(
    document_id: uuid.UUID, body: DocumentUpdate, current: AuthUser, request: Request, db: DbSession
) -> DocumentOut:
    document = access.get_document(db, current, document_id)
    access.ensure_can_modify(current, document)
    changes = body.model_dump(exclude_unset=True)
    if "title" in changes and changes["title"]:
        document.title = changes["title"].strip()
    if "category" in changes:
        document.category = (changes["category"] or "").strip() or None
    if changes.get("visibility"):
        document.visibility = Visibility(changes["visibility"])
    audit.record(
        db,
        org_id=current.org_id,
        user_id=current.id,
        action="document.updated",
        resource_type="document",
        resource_id=document.id,
        ip_address=client_ip(request),
        details={"fields": sorted(changes)},
    )
    db.flush()
    return _to_out(document)


@router.delete("/{document_id}", response_model=Message)
def delete_document(document_id: uuid.UUID, current: AuthUser, request: Request, db: DbSession) -> Message:
    document = access.get_document(db, current, document_id)
    access.ensure_can_modify(current, document)
    # Chunks are hard-deleted so the content can never be retrieved again; the document row is
    # soft-deleted to keep the audit trail and historical citations intelligible.
    db.execute(delete(DocumentChunk).where(DocumentChunk.document_id == document.id))
    db.execute(delete(CollectionDocument).where(CollectionDocument.document_id == document.id))
    document.deleted_at = datetime.now(UTC)
    document.chunk_count = 0
    storage_path = document.storage_path
    audit.record(
        db,
        org_id=current.org_id,
        user_id=current.id,
        action="document.deleted",
        resource_type="document",
        resource_id=document.id,
        ip_address=client_ip(request),
        details={"filename": document.original_filename},
    )
    db.commit()
    storage.delete_files(storage_path)
    return Message(message="Document deleted")


@router.post(
    "/{document_id}/reprocess", response_model=DocumentStatusOut, status_code=status.HTTP_202_ACCEPTED
)
def reprocess_document(
    document_id: uuid.UUID, body: ReprocessRequest, current: AuthUser, request: Request, db: DbSession
) -> DocumentStatusOut:
    document = access.get_document(db, current, document_id)
    access.ensure_can_modify(current, document)
    if document.status not in (DocumentStatus.COMPLETED, DocumentStatus.FAILED):
        raise ValidationFailedError("The document is already being processed")
    config = body.model_dump(exclude_none=True)
    job = IngestionJob(
        organization_id=current.org_id, document_id=document.id, status=DocumentStatus.QUEUED, config=config
    )
    db.add(job)
    document.status = DocumentStatus.QUEUED
    document.progress = 0
    document.error_message = None
    audit.record(
        db,
        org_id=current.org_id,
        user_id=current.id,
        action="document.reprocessed",
        resource_type="document",
        resource_id=document.id,
        ip_address=client_ip(request),
        details=config,
    )
    db.commit()
    dispatch_ingestion(document.id, current.org_id, job.id)
    db.refresh(document)
    return DocumentStatusOut(
        id=document.id,
        status=document.status.value,
        progress=document.progress,
        error_message=document.error_message,
        chunk_count=document.chunk_count,
    )


@router.get("/{document_id}/chunks", response_model=Page[ChunkOut])
def list_chunks(
    document_id: uuid.UUID,
    current: AuthUser,
    db: DbSession,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
) -> Page[ChunkOut]:
    document = access.get_document(db, current, document_id)
    base = select(DocumentChunk).where(DocumentChunk.document_id == document.id)
    total = db.scalar(select(func.count()).select_from(base.subquery())) or 0
    rows = db.scalars(
        base.order_by(DocumentChunk.chunk_index).offset((page - 1) * page_size).limit(page_size)
    ).all()
    return Page(items=[ChunkOut.model_validate(r) for r in rows], total=total, page=page, page_size=page_size)


@router.get("/{document_id}/content", response_model=DocumentContent)
def document_content(document_id: uuid.UUID, current: AuthUser, db: DbSession) -> DocumentContent:
    """Extracted, cleaned text blocks with offsets — used for preview and citation navigation."""
    document = access.get_document(db, current, document_id)
    path = storage.extracted_path(document.storage_path)
    if not path.exists():
        raise NotFoundError("The document has not been processed yet")
    data = json.loads(path.read_text(encoding="utf-8"))
    return DocumentContent(
        document_id=document.id, page_count=data.get("page_count"), blocks=data.get("blocks", [])
    )


@router.get("/{document_id}/file")
def download_file(document_id: uuid.UUID, current: AuthUser, request: Request, db: DbSession) -> FileResponse:
    document = access.get_document(db, current, document_id)
    path = storage.resolve(document.storage_path)
    if not path.exists():
        raise NotFoundError("The stored file is missing")
    audit.record(
        db,
        org_id=current.org_id,
        user_id=current.id,
        action="document.downloaded",
        resource_type="document",
        resource_id=document.id,
        ip_address=client_ip(request),
    )
    return FileResponse(
        path,
        media_type=document.mime_type,
        filename=document.original_filename,
        headers={"Content-Security-Policy": "sandbox", "X-Content-Type-Options": "nosniff"},
    )
