from __future__ import annotations

import os

import psycopg
from conftest import auth_headers, register
from fixtures import make_docx, make_markdown, make_pdf

PDF_TYPE = "application/pdf"


def upload(client, session, files, **form):  # type: ignore[no-untyped-def]
    response = client.post(
        "/api/v1/documents/upload",
        headers=auth_headers(session),
        files=[("files", f) for f in files],
        data=form,
    )
    assert response.status_code == 201, response.text
    return response.json()["results"]


def test_upload_pdf_is_processed_into_chunks(client, admin_session):
    [result] = upload(client, admin_session, [("msa.pdf", make_pdf(), PDF_TYPE)])
    assert result["outcome"] == "created"
    doc = result["document"]
    assert doc["status"] == "completed"
    assert doc["page_count"] == 3
    assert doc["chunk_count"] > 0
    assert doc["embedding_model"] == "hashing-v1"

    detail = client.get(f"/api/v1/documents/{doc['id']}", headers=auth_headers(admin_session)).json()
    timings = detail["latest_job"]["stage_timings"]
    assert {"extracting", "chunking", "embedding", "indexing"} <= set(timings)

    chunks = client.get(f"/api/v1/documents/{doc['id']}/chunks", headers=auth_headers(admin_session)).json()
    termination = next(c for c in chunks["items"] if "ninety (90) days" in c["content"])
    assert termination["page_number"] == 2
    assert termination["section"] == "4 Termination"

    content = client.get(f"/api/v1/documents/{doc['id']}/content", headers=auth_headers(admin_session)).json()
    block = next(b for b in content["blocks"] if "ninety (90) days" in b["text"])
    assert block["start"] <= termination["start_char"] <= block["end"]


def test_multiple_formats_and_status_endpoint(client, admin_session):
    results = upload(
        client,
        admin_session,
        [
            ("msa.docx", make_docx(), "application/octet-stream"),
            ("msa.md", make_markdown(), "text/markdown"),
            ("notes.txt", b"Plain notes about quarterly planning.\n\nSecond paragraph.", "text/plain"),
        ],
        category="Legal",
    )
    assert [r["outcome"] for r in results] == ["created", "created", "created"]
    doc_id = results[0]["document"]["id"]
    status = client.get(f"/api/v1/documents/{doc_id}/status", headers=auth_headers(admin_session)).json()
    assert status["status"] == "completed" and status["progress"] == 100
    listing = client.get("/api/v1/documents?category=Legal", headers=auth_headers(admin_session)).json()
    assert listing["total"] == 3


def test_duplicate_upload_detected(client, admin_session):
    data = make_pdf()
    upload(client, admin_session, [("a.pdf", data, PDF_TYPE)])
    [dup] = upload(client, admin_session, [("copy.pdf", data, PDF_TYPE)])
    assert dup["outcome"] == "duplicate"
    assert dup["duplicate_of"]


def test_invalid_files_are_rejected_individually(client, admin_session):
    results = upload(
        client,
        admin_session,
        [
            ("virus.exe", b"MZ\x90\x00", "application/octet-stream"),
            ("fake.pdf", b"just text pretending", PDF_TYPE),
            ("empty.txt", b"", "text/plain"),
            ("ok.txt", b"Valid content here.", "text/plain"),
        ],
    )
    assert [r["outcome"] for r in results] == ["rejected", "rejected", "rejected", "created"]
    assert "Unsupported file type" in results[0]["error"]


def test_upload_size_limit(client, admin_session, monkeypatch):
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "max_upload_mb", 1)
    [result] = upload(client, admin_session, [("big.txt", b"a" * (1024 * 1024 + 10), "text/plain")])
    assert result["outcome"] == "rejected"
    assert "limit" in result["error"]


def test_failed_processing_is_reported(client, admin_session):
    # A PDF header with no parseable content passes the magic-byte check but fails extraction.
    [result] = upload(client, admin_session, [("broken.pdf", b"%PDF-1.4\n garbage", PDF_TYPE)])
    doc = result["document"]
    assert doc["status"] == "failed"
    assert doc["error_message"]


def _invite(client, admin, email, role):  # type: ignore[no-untyped-def]
    token = client.post(
        "/api/v1/admin/invitations", headers=auth_headers(admin), json={"email": email, "role": role}
    ).json()["token"]
    return register(client, email, org=None, invitation_token=token)


def test_viewer_cannot_upload_or_delete(client, admin_session):
    [result] = upload(client, admin_session, [("a.txt", b"Some content.", "text/plain")])
    viewer = _invite(client, admin_session, "viewer@acme.example.com", "viewer")
    response = client.post(
        "/api/v1/documents/upload",
        headers=auth_headers(viewer),
        files=[("files", ("b.txt", b"x y z", "text/plain"))],
    )
    assert response.status_code == 403
    doc_id = result["document"]["id"]
    assert client.delete(f"/api/v1/documents/{doc_id}", headers=auth_headers(viewer)).status_code == 403
    assert client.get(f"/api/v1/documents/{doc_id}", headers=auth_headers(viewer)).status_code == 200


def test_private_documents_hidden_from_other_members(client, admin_session):
    researcher = _invite(client, admin_session, "res@acme.example.com", "researcher")
    [private] = upload(
        client, researcher, [("private.txt", b"Secret plan.", "text/plain")], visibility="private"
    )
    other = _invite(client, admin_session, "other@acme.example.com", "researcher")
    doc_id = private["document"]["id"]
    assert client.get(f"/api/v1/documents/{doc_id}", headers=auth_headers(other)).status_code == 404
    assert client.get("/api/v1/documents", headers=auth_headers(other)).json()["total"] == 0
    # Admins (documents:manage) can see private documents; owners too.
    assert client.get(f"/api/v1/documents/{doc_id}", headers=auth_headers(admin_session)).status_code == 200
    assert client.get(f"/api/v1/documents/{doc_id}", headers=auth_headers(researcher)).status_code == 200


def test_other_organization_cannot_access_documents(client, admin_session):
    [result] = upload(client, admin_session, [("msa.pdf", make_pdf(), PDF_TYPE)])
    doc_id = result["document"]["id"]
    outsider = register(client, "eve@globex.example.com", org="Globex")
    for path in ("", "/status", "/chunks", "/content", "/file"):
        assert (
            client.get(f"/api/v1/documents/{doc_id}{path}", headers=auth_headers(outsider)).status_code == 404
        )
    assert client.delete(f"/api/v1/documents/{doc_id}", headers=auth_headers(outsider)).status_code == 404
    assert client.get("/api/v1/documents", headers=auth_headers(outsider)).json()["total"] == 0
    # The same file uploaded by another organization is not a "duplicate" across tenants.
    [mine] = upload(client, outsider, [("msa.pdf", make_pdf(), PDF_TYPE)])
    assert mine["outcome"] == "created"


def test_row_level_security_blocks_cross_tenant_reads_at_database_level(client, admin_session):
    """Even a query with no WHERE clause cannot see another tenant's rows through the app role."""
    upload(client, admin_session, [("msa.pdf", make_pdf(), PDF_TYPE)])
    outsider = register(client, "eve@globex.example.com", org="Globex")
    app_url = os.environ["DATABASE_URL"].replace("postgresql+psycopg://", "postgresql://")
    with psycopg.connect(app_url) as conn:
        # No tenant set: nothing is visible.
        assert conn.execute("SELECT count(*) FROM document_chunks").fetchone()[0] == 0
        assert conn.execute("SELECT count(*) FROM documents").fetchone()[0] == 0
        # Tenant set to Globex: Acme's rows stay invisible.
        conn.execute("SELECT set_config('app.current_org', %s, true)", (outsider["organization"]["id"],))
        assert conn.execute("SELECT count(*) FROM documents").fetchone()[0] == 0
        conn.rollback()
        # Tenant set to Acme: rows are visible.
        conn.execute("SELECT set_config('app.current_org', %s, true)", (admin_session["organization"]["id"],))
        assert conn.execute("SELECT count(*) FROM document_chunks").fetchone()[0] > 0
        # Writing a row for another tenant is rejected by the WITH CHECK clause.
        try:
            conn.execute(
                "INSERT INTO audit_logs (id, organization_id, action, details, created_at) "
                "VALUES (gen_random_uuid(), %s, 'forged', '{}', now())",
                (outsider["organization"]["id"],),
            )
            raise AssertionError("cross-tenant insert should fail")
        except psycopg.errors.InsufficientPrivilege:
            conn.rollback()


def test_delete_removes_chunks_and_allows_reupload(client, admin_session):
    data = make_pdf()
    [result] = upload(client, admin_session, [("msa.pdf", data, PDF_TYPE)])
    doc_id = result["document"]["id"]
    assert (
        client.delete(f"/api/v1/documents/{doc_id}", headers=auth_headers(admin_session)).status_code == 200
    )
    assert client.get(f"/api/v1/documents/{doc_id}", headers=auth_headers(admin_session)).status_code == 404
    [again] = upload(client, admin_session, [("msa.pdf", data, PDF_TYPE)])
    assert again["outcome"] == "created"


def test_reprocess_with_new_strategy_reuses_embeddings(client, admin_session):
    [result] = upload(client, admin_session, [("msa.md", make_markdown(), "text/markdown")])
    doc_id = result["document"]["id"]
    response = client.post(
        f"/api/v1/documents/{doc_id}/reprocess",
        headers=auth_headers(admin_session),
        json={"strategy": "structure"},
    )
    assert response.status_code == 202
    detail = client.get(f"/api/v1/documents/{doc_id}", headers=auth_headers(admin_session)).json()
    assert detail["status"] == "completed"
    # Same strategy and text: every embedding is reused instead of recomputed.
    assert detail["latest_job"]["config"]["reused_embeddings"] == detail["chunk_count"]

    response = client.post(
        f"/api/v1/documents/{doc_id}/reprocess",
        headers=auth_headers(admin_session),
        json={"strategy": "recursive", "chunk_size": 300, "chunk_overlap": 60},
    )
    detail = client.get(f"/api/v1/documents/{doc_id}", headers=auth_headers(admin_session)).json()
    assert detail["chunking_strategy"] == "recursive"


def test_document_update_and_download(client, admin_session):
    [result] = upload(client, admin_session, [("q3_report.txt", b"Revenue grew.", "text/plain")])
    doc = result["document"]
    assert doc["title"] == "q3 report"
    response = client.patch(
        f"/api/v1/documents/{doc['id']}",
        headers=auth_headers(admin_session),
        json={"title": "Q3 Report", "category": "Finance"},
    )
    assert response.json()["title"] == "Q3 Report"
    file = client.get(f"/api/v1/documents/{doc['id']}/file", headers=auth_headers(admin_session))
    assert file.status_code == 200 and file.content == b"Revenue grew."
    assert file.headers["content-security-policy"] == "sandbox"
