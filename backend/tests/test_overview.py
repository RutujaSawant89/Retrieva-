from __future__ import annotations

import pytest
from conftest import auth_headers
from fixtures import make_markdown

from app.services.generation.overview import is_overview_question


@pytest.mark.parametrize(
    "question",
    [
        "what is the documenet abt ?".replace("documenet", "document"),
        "What is this document about?",
        "what is the file for",
        "Summarize the contract",
        "Can you give me an overview?",
        "What are the key points?",
        "What does this document cover?",
        "tl;dr",
    ],
)
def test_detects_overview_questions(question):
    assert is_overview_question(question)


@pytest.mark.parametrize(
    "question",
    [
        "What is the notice period for termination?",
        "How much is the annual fee?",
        "Which encryption standard protects customer data?",
    ],
)
def test_specific_questions_are_not_overviews(question):
    assert not is_overview_question(question)


def _upload(client, session, name, data):  # type: ignore[no-untyped-def]
    return client.post(
        "/api/v1/documents/upload",
        headers=auth_headers(session),
        files=[("files", (name, data, "text/markdown"))],
    ).json()["results"][0]["document"]["id"]


def _ask(client, session, question, **body):  # type: ignore[no-untyped-def]
    response = client.post(
        "/api/v1/chat/query", headers=auth_headers(session), json={"question": question, **body}
    )
    assert response.status_code == 200, response.text
    return response.json()["message"]


def test_overview_question_is_answered_from_opening_passages(client, admin_session):
    _upload(client, admin_session, "msa.md", make_markdown())
    message = _ask(client, admin_session, "what is the document abt ?")
    assert message["status"] == "answered"
    assert "[S1]" in message["content"]
    assert any(d.startswith("overview") for d in message["retrieval"]["decisions"])
    cited = [c for c in message["citations"] if c["cited_in_answer"]]
    assert cited and all(c["validation_status"] == "valid" for c in cited)


def test_overview_uses_most_recent_document_and_respects_scope(client, admin_session):
    first = _upload(
        client,
        admin_session,
        "handbook.md",
        b"# Handbook\n\nEmployees receive 25 days of annual leave per year.",
    )
    _upload(client, admin_session, "msa.md", make_markdown())
    latest = _ask(client, admin_session, "Summarize the document")
    assert "most recently uploaded" in " ".join(latest["retrieval"]["decisions"])
    assert {c["document_title"] for c in latest["citations"]} == {"msa"}

    scoped = _ask(client, admin_session, "What is this document about?", scope={"document_ids": [first]})
    assert {c["document_title"] for c in scoped["citations"]} == {"handbook"}
    assert "25 days" in scoped["content"]


def test_overview_without_documents_still_abstains(client, admin_session):
    message = _ask(client, admin_session, "What is this document about?")
    assert message["status"] == "abstained"
