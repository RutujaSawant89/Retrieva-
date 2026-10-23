from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError

from app.api.deps import CurrentUser, DbSession, client_ip, require
from app.core.errors import AppError, ConflictError, NotFoundError
from app.core.permissions import Permission
from app.db.models import CollectionDocument, Document, DocumentCollection, Visibility
from app.schemas.collections import (
    CollectionCreate,
    CollectionDocumentsChange,
    CollectionOut,
    CollectionUpdate,
)
from app.schemas.common import Message, Page
from app.services import access, audit

router = APIRouter(prefix="/collections", tags=["collections"])

Reader = Annotated[CurrentUser, Depends(require(Permission.COLLECTIONS_READ))]
Writer = Annotated[CurrentUser, Depends(require(Permission.COLLECTIONS_WRITE))]


def _document_counts(db: DbSession, current: CurrentUser, ids: list[uuid.UUID]) -> dict[uuid.UUID, int]:
    if not ids:
        return {}
    rows = db.execute(
        select(CollectionDocument.collection_id, func.count())
        .join(Document, Document.id == CollectionDocument.document_id)
        .where(CollectionDocument.collection_id.in_(ids), access.document_visibility_clause(current))
        .group_by(CollectionDocument.collection_id)
    ).all()
    return dict(rows)


def _out(collection: DocumentCollection, current: CurrentUser, count: int = 0) -> CollectionOut:
    out = CollectionOut.model_validate(collection)
    out.document_count = count
    try:
        access.ensure_can_modify_collection(current, collection)
        out.can_modify = True
    except AppError:
        out.can_modify = False
    return out


@router.post("", response_model=CollectionOut, status_code=status.HTTP_201_CREATED)
def create_collection(
    body: CollectionCreate, current: Writer, request: Request, db: DbSession
) -> CollectionOut:
    collection = DocumentCollection(
        organization_id=current.org_id,
        name=body.name.strip(),
        description=body.description.strip(),
        visibility=Visibility(body.visibility),
        created_by=current.id,
    )
    savepoint = db.begin_nested()
    try:
        db.add(collection)
        db.flush()
        savepoint.commit()
    except IntegrityError as exc:
        savepoint.rollback()
        raise ConflictError("A collection with this name already exists") from exc
    audit.record(
        db,
        org_id=current.org_id,
        user_id=current.id,
        action="collection.created",
        resource_type="collection",
        resource_id=collection.id,
        ip_address=client_ip(request),
    )
    return _out(collection, current)


@router.get("", response_model=Page[CollectionOut])
def list_collections(
    current: Reader,
    db: DbSession,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    q: str | None = Query(None, max_length=200),
) -> Page[CollectionOut]:
    stmt = select(DocumentCollection).where(access.collection_visibility_clause(current))
    if q:
        stmt = stmt.where(func.lower(DocumentCollection.name).like(f"%{q.lower()}%"))
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(
        stmt.order_by(DocumentCollection.name).offset((page - 1) * page_size).limit(page_size)
    ).all()
    counts = _document_counts(db, current, [c.id for c in rows])
    return Page(
        items=[_out(c, current, counts.get(c.id, 0)) for c in rows],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{collection_id}", response_model=CollectionOut)
def get_collection(collection_id: uuid.UUID, current: Reader, db: DbSession) -> CollectionOut:
    collection = access.get_collection(db, current, collection_id)
    return _out(collection, current, _document_counts(db, current, [collection.id]).get(collection.id, 0))


@router.patch("/{collection_id}", response_model=CollectionOut)
def update_collection(
    collection_id: uuid.UUID, body: CollectionUpdate, current: Writer, request: Request, db: DbSession
) -> CollectionOut:
    collection = access.get_collection(db, current, collection_id)
    access.ensure_can_modify_collection(current, collection)
    if body.name is not None:
        collection.name = body.name.strip()
    if body.description is not None:
        collection.description = body.description.strip()
    if body.visibility is not None:
        collection.visibility = Visibility(body.visibility)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise ConflictError("A collection with this name already exists") from exc
    audit.record(
        db,
        org_id=current.org_id,
        user_id=current.id,
        action="collection.updated",
        resource_type="collection",
        resource_id=collection.id,
        ip_address=client_ip(request),
    )
    return _out(collection, current, _document_counts(db, current, [collection.id]).get(collection.id, 0))


@router.delete("/{collection_id}", response_model=Message)
def delete_collection(collection_id: uuid.UUID, current: Writer, request: Request, db: DbSession) -> Message:
    collection = access.get_collection(db, current, collection_id)
    access.ensure_can_modify_collection(current, collection)
    db.execute(delete(CollectionDocument).where(CollectionDocument.collection_id == collection.id))
    collection.deleted_at = datetime.now(UTC)
    audit.record(
        db,
        org_id=current.org_id,
        user_id=current.id,
        action="collection.deleted",
        resource_type="collection",
        resource_id=collection.id,
        ip_address=client_ip(request),
    )
    return Message(message="Collection deleted. Its documents were not deleted.")


@router.post("/{collection_id}/documents", response_model=CollectionOut)
def add_documents(
    collection_id: uuid.UUID, body: CollectionDocumentsChange, current: Writer, db: DbSession
) -> CollectionOut:
    collection = access.get_collection(db, current, collection_id)
    access.ensure_can_modify_collection(current, collection)
    visible = set(
        db.scalars(
            select(Document.id).where(
                Document.id.in_(body.document_ids), access.document_visibility_clause(current)
            )
        )
    )
    missing = set(body.document_ids) - visible
    if missing:
        raise NotFoundError(
            "One or more documents were not found", details={"ids": [str(m) for m in missing]}
        )
    existing = set(
        db.scalars(
            select(CollectionDocument.document_id).where(
                CollectionDocument.collection_id == collection.id, CollectionDocument.document_id.in_(visible)
            )
        )
    )
    for document_id in visible - existing:
        db.add(
            CollectionDocument(
                collection_id=collection.id,
                document_id=document_id,
                organization_id=current.org_id,
                added_by=current.id,
            )
        )
    collection.updated_at = datetime.now(UTC)
    db.flush()
    return _out(collection, current, _document_counts(db, current, [collection.id]).get(collection.id, 0))


@router.delete("/{collection_id}/documents", response_model=CollectionOut)
def remove_documents(
    collection_id: uuid.UUID, body: CollectionDocumentsChange, current: Writer, db: DbSession
) -> CollectionOut:
    collection = access.get_collection(db, current, collection_id)
    access.ensure_can_modify_collection(current, collection)
    db.execute(
        delete(CollectionDocument).where(
            CollectionDocument.collection_id == collection.id,
            CollectionDocument.document_id.in_(body.document_ids),
        )
    )
    collection.updated_at = datetime.now(UTC)
    db.flush()
    return _out(collection, current, _document_counts(db, current, [collection.id]).get(collection.id, 0))
