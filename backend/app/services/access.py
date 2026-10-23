"""Document- and collection-level authorization filters.

Organization isolation is enforced twice: by these application filters and by PostgreSQL
Row-Level Security. Within an organization, ``private`` documents and collections are visible
only to their owner and to users with ``documents:manage`` (admins).
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import ColumnElement, and_, or_, select
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError, PermissionDeniedError
from app.core.permissions import Permission
from app.db.models import CollectionDocument, Document, DocumentCollection, Visibility

if TYPE_CHECKING:
    from app.api.deps import CurrentUser


def document_visibility_for(org_id: uuid.UUID, user_id: uuid.UUID, can_manage: bool) -> ColumnElement[bool]:
    clauses = [Document.organization_id == org_id, Document.deleted_at.is_(None)]
    if not can_manage:
        clauses.append(or_(Document.visibility == Visibility.ORGANIZATION, Document.owner_id == user_id))
    return and_(*clauses)


def document_visibility_clause(current: CurrentUser) -> ColumnElement[bool]:
    return document_visibility_for(current.org_id, current.id, current.can(Permission.DOCUMENTS_MANAGE))


def collection_visibility_clause(current: CurrentUser) -> ColumnElement[bool]:
    clauses = [DocumentCollection.organization_id == current.org_id, DocumentCollection.deleted_at.is_(None)]
    if not current.can(Permission.DOCUMENTS_MANAGE):
        clauses.append(
            or_(
                DocumentCollection.visibility == Visibility.ORGANIZATION,
                DocumentCollection.created_by == current.id,
            )
        )
    return and_(*clauses)


def get_document(db: Session, current: CurrentUser, document_id: uuid.UUID) -> Document:
    document = db.scalar(
        select(Document).where(Document.id == document_id, document_visibility_clause(current))
    )
    if document is None:
        # 404 rather than 403: do not reveal that a document exists in another tenant/scope.
        raise NotFoundError("Document not found")
    return document


def ensure_can_modify(current: CurrentUser, document: Document) -> None:
    if current.can(Permission.DOCUMENTS_MANAGE):
        return
    if current.can(Permission.DOCUMENTS_WRITE) and document.owner_id == current.id:
        return
    raise PermissionDeniedError("You can only modify documents you uploaded")


def get_collection(db: Session, current: CurrentUser, collection_id: uuid.UUID) -> DocumentCollection:
    collection = db.scalar(
        select(DocumentCollection).where(
            DocumentCollection.id == collection_id, collection_visibility_clause(current)
        )
    )
    if collection is None:
        raise NotFoundError("Collection not found")
    return collection


def ensure_can_modify_collection(current: CurrentUser, collection: DocumentCollection) -> None:
    if current.can(Permission.DOCUMENTS_MANAGE):
        return
    if current.can(Permission.COLLECTIONS_WRITE) and (
        collection.visibility == Visibility.ORGANIZATION or collection.created_by == current.id
    ):
        return
    raise PermissionDeniedError("You cannot modify this collection")


def resolve_scope_document_ids(
    db: Session,
    current: CurrentUser,
    document_ids: list[uuid.UUID] | None,
    collection_ids: list[uuid.UUID] | None,
) -> list[uuid.UUID] | None:
    """Expand a retrieval scope to the concrete document IDs the user may search.

    Returns ``None`` for "the whole knowledge base the user can see". Requested documents or
    collections the user cannot see are rejected with 404 so scope cannot be used to probe.
    """
    if not document_ids and not collection_ids:
        return None
    allowed: set[uuid.UUID] = set()
    if document_ids:
        visible = set(
            db.scalars(
                select(Document.id).where(Document.id.in_(document_ids), document_visibility_clause(current))
            )
        )
        missing = set(document_ids) - visible
        if missing:
            raise NotFoundError(
                "One or more documents were not found", details={"ids": [str(m) for m in missing]}
            )
        allowed |= visible
    if collection_ids:
        visible_collections = set(
            db.scalars(
                select(DocumentCollection.id).where(
                    DocumentCollection.id.in_(collection_ids), collection_visibility_clause(current)
                )
            )
        )
        missing = set(collection_ids) - visible_collections
        if missing:
            raise NotFoundError(
                "One or more collections were not found", details={"ids": [str(m) for m in missing]}
            )
        allowed |= set(
            db.scalars(
                select(Document.id)
                .join(CollectionDocument, CollectionDocument.document_id == Document.id)
                .where(
                    CollectionDocument.collection_id.in_(visible_collections),
                    document_visibility_clause(current),
                )
            )
        )
    return sorted(allowed)
