from __future__ import annotations

import psycopg
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
    client.cookies.set("retrieva_refresh", value, path="/api/v1/auth")


def test_refresh_rotates_and_detects_reuse(client, admin_db_url):
    register(client, "rotate@acme.example.com")
    first_cookie = client.cookies.get("retrieva_refresh")

    rotated = client.post("/api/v1/auth/refresh")
    assert rotated.status_code == 200
    second_cookie = client.cookies.get("retrieva_refresh")
    assert second_cookie and second_cookie != first_cookie

    # Age the rotation past the concurrent-refresh grace window.
    with psycopg.connect(admin_db_url, autocommit=True) as conn:
        conn.execute(
            "UPDATE refresh_tokens SET revoked_at = now() - interval '1 hour' WHERE revoked_at IS NOT NULL"
        )

    # Replaying the old token revokes the whole family, including the newest token.
    _use_cookie(client, first_cookie)
    replay = client.post("/api/v1/auth/refresh")
    assert replay.status_code == 401
    _use_cookie(client, second_cookie)
    assert client.post("/api/v1/auth/refresh").status_code == 401


def test_concurrent_refresh_race_is_not_treated_as_theft(client):
    register(client, "race@acme.example.com")
    first_cookie = client.cookies.get("retrieva_refresh")
    assert client.post("/api/v1/auth/refresh").status_code == 200
    second_cookie = client.cookies.get("retrieva_refresh")

    # A second tab presents the just-rotated token: rejected softly, family stays valid.
    _use_cookie(client, first_cookie)
    raced = client.post("/api/v1/auth/refresh")
    assert raced.status_code == 401
    assert raced.json()["error"]["code"] == "refresh_race"
    _use_cookie(client, second_cookie)
    assert client.post("/api/v1/auth/refresh").status_code == 200


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
