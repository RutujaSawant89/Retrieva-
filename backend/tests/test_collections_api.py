from __future__ import annotations

from conftest import auth_headers, register


def _upload(client, session, name, text):  # type: ignore[no-untyped-def]
    response = client.post(
        "/api/v1/documents/upload",
        headers=auth_headers(session),
        files=[("files", (name, text, "text/plain"))],
    )
    return response.json()["results"][0]["document"]["id"]


def test_collection_lifecycle_and_scoped_search(client, admin_session):
    h = auth_headers(admin_session)
    finance = _upload(client, admin_session, "finance.txt", b"Quarterly revenue reached 12 million dollars.")
    legal = _upload(client, admin_session, "legal.txt", b"The contract renews automatically every year.")

    created = client.post("/api/v1/collections", headers=h, json={"name": "Financial Reports"}).json()
    cid = created["id"]
    assert (
        client.post("/api/v1/collections", headers=h, json={"name": "financial reports"}).status_code == 409
    )

    added = client.post(
        f"/api/v1/collections/{cid}/documents", headers=h, json={"document_ids": [finance]}
    ).json()
    assert added["document_count"] == 1
    listing = client.get(f"/api/v1/documents?collection_id={cid}", headers=h).json()
    assert [d["id"] for d in listing["items"]] == [finance]

    # Search restricted to the collection never returns the legal document.
    body = {"query": "contract renews revenue", "scope": {"collection_ids": [cid]}}
    results = client.post("/api/v1/search", headers=h, json=body).json()["results"]
    assert results and all(r["document_id"] == finance for r in results)

    renamed = client.patch(f"/api/v1/collections/{cid}", headers=h, json={"name": "Finance"}).json()
    assert renamed["name"] == "Finance"
    removed = client.request(
        "DELETE", f"/api/v1/collections/{cid}/documents", headers=h, json={"document_ids": [finance]}
    )
    assert removed.json()["document_count"] == 0
    assert client.delete(f"/api/v1/collections/{cid}", headers=h).status_code == 200
    assert client.get(f"/api/v1/collections/{cid}", headers=h).status_code == 404
    # Deleting a collection keeps its documents.
    assert client.get(f"/api/v1/documents/{legal}", headers=h).status_code == 200


def test_collections_are_isolated_between_organizations(client, admin_session):
    cid = client.post(
        "/api/v1/collections", headers=auth_headers(admin_session), json={"name": "Secret"}
    ).json()["id"]
    outsider = register(client, "eve@globex.example.com", org="Globex")
    assert client.get(f"/api/v1/collections/{cid}", headers=auth_headers(outsider)).status_code == 404
    assert client.get("/api/v1/collections", headers=auth_headers(outsider)).json()["total"] == 0
    body = {"query": "anything", "scope": {"collection_ids": [cid]}}
    assert client.post("/api/v1/search", headers=auth_headers(outsider), json=body).status_code == 404


def test_viewer_cannot_modify_collections(client, admin_session):
    cid = client.post(
        "/api/v1/collections", headers=auth_headers(admin_session), json={"name": "Shared"}
    ).json()["id"]
    token = client.post(
        "/api/v1/admin/invitations",
        headers=auth_headers(admin_session),
        json={"email": "v@acme.example.com", "role": "viewer"},
    ).json()["token"]
    viewer = register(client, "v@acme.example.com", org=None, invitation_token=token)
    assert client.get(f"/api/v1/collections/{cid}", headers=auth_headers(viewer)).status_code == 200
    assert client.delete(f"/api/v1/collections/{cid}", headers=auth_headers(viewer)).status_code == 403
    assert (
        client.post("/api/v1/collections", headers=auth_headers(viewer), json={"name": "Mine"}).status_code
        == 403
    )


def test_private_collection_hidden_from_other_members(client, admin_session):
    token = client.post(
        "/api/v1/admin/invitations",
        headers=auth_headers(admin_session),
        json={"email": "r@acme.example.com", "role": "researcher"},
    ).json()["token"]
    researcher = register(client, "r@acme.example.com", org=None, invitation_token=token)
    cid = client.post(
        "/api/v1/collections",
        headers=auth_headers(researcher),
        json={"name": "Draft", "visibility": "private"},
    ).json()["id"]
    token2 = client.post(
        "/api/v1/admin/invitations",
        headers=auth_headers(admin_session),
        json={"email": "r2@acme.example.com", "role": "researcher"},
    ).json()["token"]
    other = register(client, "r2@acme.example.com", org=None, invitation_token=token2)
    assert client.get(f"/api/v1/collections/{cid}", headers=auth_headers(other)).status_code == 404
    assert client.get(f"/api/v1/collections/{cid}", headers=auth_headers(admin_session)).status_code == 200
