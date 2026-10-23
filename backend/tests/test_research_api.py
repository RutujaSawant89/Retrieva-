from __future__ import annotations

import io
import json

from conftest import auth_headers, register
from fixtures import CONTRACT_SECTIONS, make_markdown

AMENDED = [
    (heading, body.replace("48,000 USD", "52,000 USD").replace("ninety (90)", "sixty (60)"))
    for heading, body in CONTRACT_SECTIONS
] + [
    ("6 Audit Rights", "The Customer may audit the Provider once per calendar year with thirty days notice.")
]


def _upload(client, session, name, data):  # type: ignore[no-untyped-def]
    response = client.post(
        "/api/v1/documents/upload",
        headers=auth_headers(session),
        files=[("files", (name, data, "text/markdown"))],
    )
    return response.json()["results"][0]["document"]["id"]


def _sse(text: str) -> list[tuple[str, dict]]:
    events = []
    for block in text.strip().split("\n\n"):
        fields = dict(line.split(": ", 1) for line in block.splitlines() if ": " in line)
        events.append((fields["event"], json.loads(fields["data"])))
    return events


def test_compare_detects_changes_contradictions_and_additions(client, admin_session):
    a = _upload(client, admin_session, "msa-2023.md", make_markdown())
    b = _upload(client, admin_session, "msa-2024.md", make_markdown(AMENDED))
    result = client.post(
        "/api/v1/compare", headers=auth_headers(admin_session), json={"document_a": a, "document_b": b}
    ).json()
    reasons = " ".join(c["reason"] for c in result["contradictions"])
    assert "48000" in reasons and "52000" in reasons
    assert any("60" in c["reason"] for c in result["contradictions"])
    # The new audit clause appears either as B-only or inside a changed passage, depending on chunking.
    b_texts = [p["text"] for p in result["only_b"]] + [
        a["b"]["text"] for a in result["alignments"] if a["kind"] == "changed"
    ]
    assert any("Audit" in text for text in b_texts)
    assert result["stats"]["same"] >= 1
    # Extractive mode: no narrative summary is invented.
    assert result["summary"] is None and result["summary_note"]


def test_compare_rejects_inaccessible_documents(client, admin_session):
    a = _upload(client, admin_session, "a.md", make_markdown())
    outsider = register(client, "eve@globex.example.com", org="Globex")
    b = _upload(client, outsider, "b.md", make_markdown(AMENDED))
    response = client.post(
        "/api/v1/compare", headers=auth_headers(outsider), json={"document_a": a, "document_b": b}
    )
    assert response.status_code == 404


def test_research_stream_and_exports(client, admin_session):
    _upload(client, admin_session, "msa.md", make_markdown())
    response = client.post(
        "/api/v1/research",
        headers=auth_headers(admin_session),
        json={"question": "What are the termination terms and how is customer data protected?"},
    )
    events = _sse(response.text)
    names = [name for name, _ in events]
    assert names[0] == "meta" and names[-1] == "done"
    assert {"plan", "subquery", "evidence", "verification"} <= set(names)
    plan = dict(events)["plan"]
    assert len(plan["subqueries"]) >= 2
    report_id = events[-1][1]["report_id"]

    report = client.get(f"/api/v1/research/{report_id}", headers=auth_headers(admin_session)).json()
    assert report["status"] == "completed"
    assert "ninety (90) days" in report["report"] and "AES-256" in report["report"]
    assert report["verification"]["citation_validity"] == 1.0

    md = client.get(f"/api/v1/research/{report_id}/export?format=md", headers=auth_headers(admin_session))
    assert md.status_code == 200 and "**Sources**" in md.text and "[S1]" in md.text
    docx = client.get(f"/api/v1/research/{report_id}/export?format=docx", headers=auth_headers(admin_session))
    import docx as python_docx

    text = "\n".join(p.text for p in python_docx.Document(io.BytesIO(docx.content)).paragraphs)
    assert "Sources" in text and "[S1]" in text
    pdf = client.get(f"/api/v1/research/{report_id}/export?format=pdf", headers=auth_headers(admin_session))
    assert pdf.content.startswith(b"%PDF")
    assert "attachment" in pdf.headers["content-disposition"]

    listing = client.get("/api/v1/research", headers=auth_headers(admin_session)).json()
    assert listing["total"] == 1
    assert (
        client.delete(f"/api/v1/research/{report_id}", headers=auth_headers(admin_session)).status_code == 200
    )
    assert client.get(f"/api/v1/research/{report_id}", headers=auth_headers(admin_session)).status_code == 404


def test_research_requires_permission(client, admin_session):
    token = client.post(
        "/api/v1/admin/invitations",
        headers=auth_headers(admin_session),
        json={"email": "v@acme.example.com", "role": "viewer"},
    ).json()["token"]
    viewer = register(client, "v@acme.example.com", org=None, invitation_token=token)
    response = client.post(
        "/api/v1/research", headers=auth_headers(viewer), json={"question": "What is the fee?"}
    )
    assert response.status_code == 403


def test_conversation_export(client, admin_session):
    _upload(client, admin_session, "msa.md", make_markdown())
    answer = client.post(
        "/api/v1/chat/query",
        headers=auth_headers(admin_session),
        json={"question": "What is the annual subscription fee?"},
    ).json()
    cid = answer["conversation_id"]
    md = client.get(f"/api/v1/conversations/{cid}/export?format=md", headers=auth_headers(admin_session))
    assert "48,000 USD" in md.text and "**Sources**" in md.text
    pdf = client.get(f"/api/v1/conversations/{cid}/export?format=pdf", headers=auth_headers(admin_session))
    assert pdf.content.startswith(b"%PDF")
