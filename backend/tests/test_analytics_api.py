from __future__ import annotations

from conftest import auth_headers, register
from fixtures import make_pdf


def test_overview_reflects_real_activity(client, admin_session):
    h = auth_headers(admin_session)
    empty = client.get("/api/v1/analytics/overview", headers=h).json()
    assert empty["documents"]["total"] == 0
    assert empty["queries"]["retrieval_success_rate"] is None  # no data is not "0%"

    client.post(
        "/api/v1/documents/upload", headers=h, files=[("files", ("msa.pdf", make_pdf(), "application/pdf"))]
    )
    client.post(
        "/api/v1/documents/upload",
        headers=h,
        files=[("files", ("bad.pdf", b"%PDF-1.4 junk", "application/pdf"))],
    )
    client.post("/api/v1/search", headers=h, json={"query": "termination notice"})
    client.post(
        "/api/v1/chat/query",
        headers=h,
        json={"question": "What notice is required to terminate for convenience?"},
    )
    client.post(
        "/api/v1/chat/query", headers=h, json={"question": "What is the boiling point of mercury on Mars?"}
    )

    data = client.get("/api/v1/analytics/overview", headers=h).json()
    assert data["documents"]["total"] == 2
    assert data["documents"]["indexed"] == 1
    assert data["documents"]["failed"] == 1
    assert data["failed_ingestion_jobs"] == 1
    assert data["documents"]["chunks"] > 0
    assert data["queries"]["total"] == 3
    assert data["answers"]["total"] == 2
    assert data["answers"]["abstained"] == 1
    assert data["answers"]["abstention_rate"] == 0.5
    assert data["answers"]["citation_validity_rate"] == 1.0
    assert data["conversations"] == 2


def test_retrieval_and_usage_series(client, admin_session):
    h = auth_headers(admin_session)
    client.post(
        "/api/v1/documents/upload", headers=h, files=[("files", ("msa.pdf", make_pdf(), "application/pdf"))]
    )
    for strategy in ("dense", "sparse", "hybrid"):
        client.post(
            "/api/v1/search", headers=h, json={"query": "data protection", "options": {"strategy": strategy}}
        )
    retrieval = client.get("/api/v1/analytics/retrieval?days=7", headers=h).json()
    assert {row["strategy"] for row in retrieval["by_strategy"]} == {"dense", "sparse", "hybrid"}
    assert retrieval["latency"][-1]["queries"] == 3
    assert any(row["stage"] == "fusion" for row in retrieval["stage_ms"])

    usage = client.get("/api/v1/analytics/usage?days=7", headers=h).json()
    assert len(usage["series"]) == 7
    assert usage["series"][-1]["queries"] == 3
    assert usage["series"][-1]["uploads"] == 1
    assert usage["active_users"] == 1


def test_analytics_permissions_and_isolation(client, admin_session):
    h = auth_headers(admin_session)
    client.post(
        "/api/v1/documents/upload", headers=h, files=[("files", ("msa.pdf", make_pdf(), "application/pdf"))]
    )
    outsider = register(client, "eve@globex.example.com", org="Globex")
    assert (
        client.get("/api/v1/analytics/overview", headers=auth_headers(outsider)).json()["documents"]["total"]
        == 0
    )
    token = client.post(
        "/api/v1/admin/invitations", headers=h, json={"email": "v@acme.example.com", "role": "viewer"}
    ).json()["token"]
    viewer = register(client, "v@acme.example.com", org=None, invitation_token=token)
    assert client.get("/api/v1/analytics/overview", headers=auth_headers(viewer)).status_code == 200
    assert client.get("/api/v1/analytics/retrieval", headers=auth_headers(viewer)).status_code == 403
