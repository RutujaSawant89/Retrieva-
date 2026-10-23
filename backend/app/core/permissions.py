"""Role-based access control: roles, permissions and their mapping.

Roles are also stored in the ``roles`` table (seeded by migration) so they are visible to SQL
tooling, but this module is the source of truth used for authorization checks.
"""

from __future__ import annotations

import enum


class Permission(enum.StrEnum):
    DOCUMENTS_READ = "documents:read"
    DOCUMENTS_WRITE = "documents:write"  # upload, edit metadata, delete own documents
    DOCUMENTS_MANAGE = "documents:manage"  # delete/modify any document, see private documents
    COLLECTIONS_READ = "collections:read"
    COLLECTIONS_WRITE = "collections:write"
    CHAT = "chat:use"
    SEARCH = "search:use"
    RESEARCH = "research:use"
    ANALYTICS_READ = "analytics:read"
    EVALUATION_READ = "evaluation:read"
    EVALUATION_RUN = "evaluation:run"
    MEMBERS_MANAGE = "members:manage"
    AUDIT_READ = "audit:read"


class RoleName(enum.StrEnum):
    ADMIN = "admin"
    ANALYST = "analyst"
    RESEARCHER = "researcher"
    VIEWER = "viewer"


_READ = {
    Permission.DOCUMENTS_READ,
    Permission.COLLECTIONS_READ,
    Permission.CHAT,
    Permission.SEARCH,
}

ROLE_PERMISSIONS: dict[RoleName, frozenset[Permission]] = {
    RoleName.ADMIN: frozenset(Permission),
    RoleName.ANALYST: frozenset(
        _READ
        | {
            Permission.DOCUMENTS_WRITE,
            Permission.COLLECTIONS_WRITE,
            Permission.RESEARCH,
            Permission.ANALYTICS_READ,
            Permission.EVALUATION_READ,
            Permission.EVALUATION_RUN,
        }
    ),
    RoleName.RESEARCHER: frozenset(
        _READ
        | {
            Permission.DOCUMENTS_WRITE,
            Permission.COLLECTIONS_WRITE,
            Permission.RESEARCH,
            Permission.EVALUATION_READ,
        }
    ),
    RoleName.VIEWER: frozenset(_READ),
}

ROLE_DESCRIPTIONS: dict[RoleName, str] = {
    RoleName.ADMIN: "Full control of the organization, its members, documents and audit logs.",
    RoleName.ANALYST: "Uploads documents, runs evaluations and reads analytics.",
    RoleName.RESEARCHER: "Uploads documents, builds collections, chats and runs research.",
    RoleName.VIEWER: "Searches and chats over documents shared with the organization.",
}

ROLE_IDS: dict[RoleName, int] = {
    RoleName.ADMIN: 1,
    RoleName.ANALYST: 2,
    RoleName.RESEARCHER: 3,
    RoleName.VIEWER: 4,
}


def permissions_for(role: str) -> frozenset[Permission]:
    try:
        return ROLE_PERMISSIONS[RoleName(role)]
    except ValueError:
        return frozenset()


def has_permission(role: str, permission: Permission) -> bool:
    return permission in permissions_for(role)
