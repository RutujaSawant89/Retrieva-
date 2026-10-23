"""ASGI middleware: correlation IDs, security headers, request metrics and API usage records.

Implemented as plain ASGI middleware (not ``BaseHTTPMiddleware``) so streaming responses are
passed through untouched.
"""

from __future__ import annotations

import logging
import re
import time
import uuid

import anyio
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.logging import correlation_id_var
from app.core.metrics import HTTP_LATENCY, HTTP_REQUESTS

logger = logging.getLogger("retrieva.access")

_SAFE_CID = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
_SECURITY_HEADERS = [
    (b"x-content-type-options", b"nosniff"),
    (b"x-frame-options", b"DENY"),
    (b"referrer-policy", b"no-referrer"),
    (b"cross-origin-opener-policy", b"same-origin"),
]


def _route_template(scope: Scope) -> str:
    route = scope.get("route")
    return getattr(route, "path", None) or "unmatched"


class RequestContextMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = dict(scope.get("headers") or [])
        incoming = headers.get(b"x-correlation-id", b"").decode("latin-1")
        cid = incoming if _SAFE_CID.match(incoming) else uuid.uuid4().hex
        token = correlation_id_var.set(cid)
        scope.setdefault("state", {})
        scope["state"]["correlation_id"] = cid
        start = time.perf_counter()
        status_holder = {"status": 500}

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                status_holder["status"] = message["status"]
                raw = list(message.get("headers", []))
                raw.append((b"x-correlation-id", cid.encode()))
                raw.extend(_SECURITY_HEADERS)
                message["headers"] = raw
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            elapsed = time.perf_counter() - start
            method = scope.get("method", "GET")
            route = _route_template(scope)
            status = status_holder["status"]
            HTTP_REQUESTS.labels(method, route, str(status)).inc()
            HTTP_LATENCY.labels(method, route).observe(elapsed)
            if route != "/metrics" and route != "/health/live":
                logger.info(
                    "request",
                    extra={
                        "method": method,
                        "route": route,
                        "status": status,
                        "latency_ms": round(elapsed * 1000, 1),
                    },
                )
            usage = scope["state"].get("usage")
            if usage is not None and route.startswith("/api/"):
                await anyio.to_thread.run_sync(
                    _record_usage, usage, method, route, status, elapsed * 1000, cid
                )
            correlation_id_var.reset(token)


def _record_usage(usage: dict, method: str, route: str, status: int, latency_ms: float, cid: str) -> None:
    from app.db.models import ApiUsage
    from app.db.session import session_scope

    try:
        with session_scope(usage["org_id"]) as session:
            session.add(
                ApiUsage(
                    organization_id=usage["org_id"],
                    user_id=usage.get("user_id"),
                    method=method,
                    route=route[:255],
                    status_code=status,
                    latency_ms=latency_ms,
                    prompt_tokens=usage.get("prompt_tokens", 0),
                    completion_tokens=usage.get("completion_tokens", 0),
                    correlation_id=cid,
                )
            )
    except Exception:  # usage accounting must never break a request
        logger.warning("api_usage_record_failed", exc_info=True)
