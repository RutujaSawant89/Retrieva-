from __future__ import annotations

from conftest import STRONG_PASSWORD, auth_headers, register


def test_register_creates_org_and_admin(client):
    session = register(client, "founder@acme.example.com", org="Acme")
    assert session["organization"]["name"] == "Acme"
    assert session["organization"]["role"] == "admin"
    assert "members:manage" in session["permissions"]
    assert "retrieva_refresh" in client.cookies
    # The refresh token must never be returned in the JSON body.
    assert "refresh_token" not in session


def test_register_rejects_weak_password(client):
    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": "weak@acme.example.com",
            "full_name": "Weak",
            "password": "password",
            "organization_name": "Acme",
        },
    )
    assert response.status_code == 422
    body = response.json()["error"]
    assert body["code"] == "validation_error"
    assert any(f["field"] == "password" for f in body["details"]["fields"])


def test_register_duplicate_email_conflicts(client):
    register(client, "dup@acme.example.com")
    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": "DUP@acme.example.com",
            "full_name": "Dup",
            "password": STRONG_PASSWORD,
            "organization_name": "Xco",
        },
    )
    assert response.status_code == 409


def test_login_and_me(client):
    register(client, "user@acme.example.com")
    client.cookies.clear()
    response = client.post(
        "/api/v1/auth/login", json={"email": "USER@acme.example.com", "password": STRONG_PASSWORD}
    )
    assert response.status_code == 200
    me = client.get("/api/v1/auth/me", headers=auth_headers(response.json()))
    assert me.status_code == 200
    assert me.json()["email"] == "user@acme.example.com"


def test_login_wrong_password_is_generic(client):
    register(client, "user@acme.example.com")
    wrong = client.post(
        "/api/v1/auth/login", json={"email": "user@acme.example.com", "password": "Wrong-Pass-123"}
    )
    unknown = client.post(
        "/api/v1/auth/login", json={"email": "nobody@acme.example.com", "password": "Wrong-Pass-123"}
    )
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json()["error"]["message"] == unknown.json()["error"]["message"]


def test_protected_route_requires_token(client):
    assert client.get("/api/v1/auth/me").status_code == 401
    bad = client.get("/api/v1/auth/me", headers={"Authorization": "Bearer not-a-jwt"})
    assert bad.status_code == 401


def _use_cookie(client, value):  # type: ignore[no-untyped-def]
    client.cookies.clear()
    client.cookies.set("retrieva_refresh", value, domain="testserver.local", path="/api/v1/auth")


def test_refresh_rotates_and_detects_reuse(client):
    register(client, "rotate@acme.example.com")
    first = client.cookies.get("retrieva_refresh")
    assert client.post("/api/v1/auth/refresh").status_code == 200
    second = client.cookies.get("retrieva_refresh")
    assert second and second != first
    # The legitimate client keeps rotating, so the successor of `first` has been used.
    assert client.post("/api/v1/auth/refresh").status_code == 200
    third = client.cookies.get("retrieva_refresh")

    # Replaying `first` is theft: the whole family is revoked, including the newest token.
    _use_cookie(client, first)
    assert client.post("/api/v1/auth/refresh").status_code == 401
    _use_cookie(client, third)
    assert client.post("/api/v1/auth/refresh").status_code == 401


def test_lost_refresh_response_does_not_log_out(client):
    """A rotation whose response never reached the client, or a concurrent tab, is recoverable."""
    register(client, "race@acme.example.com")
    t1 = client.cookies.get("retrieva_refresh")
    assert client.post("/api/v1/auth/refresh").status_code == 200
    t2 = client.cookies.get("retrieva_refresh")

    # The browser never stored t2 and presents t1 again: re-issued, not treated as theft.
    _use_cookie(client, t1)
    assert client.post("/api/v1/auth/refresh").status_code == 200
    t3 = client.cookies.get("retrieva_refresh")

    # Concurrent tabs: the browser kept the superseded t2 instead of t3. Still recoverable.
    _use_cookie(client, t2)
    assert client.post("/api/v1/auth/refresh").status_code == 200
    t4 = client.cookies.get("retrieva_refresh")
    assert len({t1, t2, t3, t4}) == 4

    # Normal use continues on the newest token...
    assert client.post("/api/v1/auth/refresh").status_code == 200
    t5 = client.cookies.get("retrieva_refresh")
    # ...and replaying a token whose chain has moved on is still detected as theft.
    _use_cookie(client, t1)
    assert client.post("/api/v1/auth/refresh").status_code == 401
    _use_cookie(client, t5)
    assert client.post("/api/v1/auth/refresh").status_code == 401


def test_logout_revokes_refresh_token(client):
    register(client, "bye@acme.example.com")
    cookie = client.cookies.get("retrieva_refresh")
    assert client.post("/api/v1/auth/logout").status_code == 200
    client.cookies.clear()
    client.cookies.set("retrieva_refresh", cookie, path="/api/v1/auth")
    assert client.post("/api/v1/auth/refresh").status_code == 401


def test_change_password(client):
    session = register(client, "pw@acme.example.com")
    response = client.post(
        "/api/v1/auth/me/password",
        headers=auth_headers(session),
        json={"current_password": STRONG_PASSWORD, "new_password": "An0ther-Strong-Pass"},
    )
    assert response.status_code == 200
    ok = client.post(
        "/api/v1/auth/login", json={"email": "pw@acme.example.com", "password": "An0ther-Strong-Pass"}
    )
    assert ok.status_code == 200


def test_error_responses_carry_correlation_id(client):
    response = client.get("/api/v1/auth/me", headers={"X-Correlation-ID": "abc-123"})
    assert response.headers["x-correlation-id"] == "abc-123"
    assert response.json()["error"]["correlation_id"] == "abc-123"
