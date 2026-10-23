"""Row-Level Security plumbing.

RLS policies compare ``organization_id`` with the transaction-local setting
``app.current_org``. ``bind_tenant`` records the tenant on the session and applies it to the
current transaction; ``apply_tenant_on_begin`` re-applies it whenever the session starts a new
transaction (e.g. after a commit). ``set_config(..., is_local => true)`` scopes the value to the
transaction, so a pooled connection can never carry one tenant's setting into another request.
"""

from __future__ import annotations

import uuid

from sqlalchemy import text
from sqlalchemy.orm import Session

_TENANT_KEY = "tenant_org_id"
_SET_SQL = text("SELECT set_config('app.current_org', :org, true)")


def bind_tenant(session: Session, org_id: object) -> None:
    org = str(uuid.UUID(str(org_id)))
    session.info[_TENANT_KEY] = org
    if session.in_transaction():
        session.execute(_SET_SQL, {"org": org})


def current_tenant(session: Session) -> str | None:
    return session.info.get(_TENANT_KEY)


def apply_tenant_on_begin(session: Session, transaction: object, connection: object) -> None:
    org = session.info.get(_TENANT_KEY)
    if org is not None:
        connection.execute(_SET_SQL, {"org": org})  # type: ignore[attr-defined]
