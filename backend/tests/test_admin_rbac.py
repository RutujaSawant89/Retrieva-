from __future__ import annotations

from conftest import STRONG_PASSWORD, auth_headers, register


def _invite(client, admin, email, role):  # type: ignore[no-untyped-def]
    response = client.post(
        "/api/v1/admin/invitations", headers=auth_headers(admin), json={"email": email, "role": role}
    )
    assert response.status_code == 201, response.text
    return response.json()["token"]


def test_invitation_flow_assigns_role(client, admin_session):
    token = _invite(client, admin_session, "viewer@acme.example.com", "viewer")
    viewer = register(client, "viewer@acme.example.com", org=None, invitation_token=token)
    assert viewer["organization"]["id"] == admin_session["organization"]["id"]
    assert viewer["organization"]["role"] == "viewer"
    assert "documents:write" not in viewer["permissions"]


def test_invitation_cannot_be_used_by_other_email(client, admin_session):
    token = _invite(client, admin_session, "a@acme.example.com", "analyst")
    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": "b@acme.example.com",
            "full_name": "B",
            "password": STRONG_PASSWORD,
            "invitation_token": token,
        },
    )
    assert response.status_code == 422


def test_viewer_cannot_use_admin_endpoints(client, admin_session):
    token = _invite(client, admin_session, "viewer@acme.example.com", "viewer")
    viewer = register(client, "viewer@acme.example.com", org=None, invitation_token=token)
    assert client.get("/api/v1/admin/users", headers=auth_headers(viewer)).status_code == 403
    assert client.get("/api/v1/admin/audit-logs", headers=auth_headers(viewer)).status_code == 403


def test_role_change_takes_effect_immediately(client, admin_session):
    token = _invite(client, admin_session, "analyst@acme.example.com", "analyst")
    analyst = register(client, "analyst@acme.example.com", org=None, invitation_token=token)
    response = client.patch(
        f"/api/v1/admin/users/{analyst['user']['id']}",
        headers=auth_headers(admin_session),
        json={"role": "admin"},
    )
    assert response.status_code == 200
    # The analyst's existing access token now carries admin rights (membership is re-read per request).
    assert client.get("/api/v1/admin/users", headers=auth_headers(analyst)).status_code == 200


def test_last_admin_cannot_be_demoted(client, admin_session):
    response = client.patch(
        f"/api/v1/admin/users/{admin_session['user']['id']}",
        headers=auth_headers(admin_session),
        json={"role": "viewer"},
    )
    assert response.status_code == 409


def test_removed_member_loses_access(client, admin_session):
    token = _invite(client, admin_session, "temp@acme.example.com", "researcher")
    temp = register(client, "temp@acme.example.com", org=None, invitation_token=token)
    assert client.get("/api/v1/auth/me", headers=auth_headers(temp)).status_code == 200
    client.delete(f"/api/v1/admin/users/{temp['user']['id']}", headers=auth_headers(admin_session))
    assert client.get("/api/v1/auth/me", headers=auth_headers(temp)).status_code == 401


def test_admin_cannot_see_other_org_members(client, admin_session):
    other = register(client, "other@globex.example.com", org="Globex")
    users = client.get("/api/v1/admin/users", headers=auth_headers(admin_session)).json()
    emails = {u["email"] for u in users["items"]}
    assert "other@globex.example.com" not in emails
    assert client.get("/api/v1/admin/users", headers=auth_headers(other)).json()["total"] == 1


def test_audit_log_records_login(client, admin_session):
    client.post("/api/v1/auth/login", json={"email": "admin@acme.example.com", "password": STRONG_PASSWORD})
    logs = client.get("/api/v1/admin/audit-logs", headers=auth_headers(admin_session)).json()
    actions = [item["action"] for item in logs["items"]]
    assert "auth.register" in actions and "auth.login" in actions
