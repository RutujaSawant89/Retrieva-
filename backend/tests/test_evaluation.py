from __future__ import annotations

import json
import math

import pytest
from conftest import auth_headers, register
from fixtures import make_markdown

from app.services.evaluation import metrics as m
from app.services.evaluation.datasets import parse_dataset_file

# ------------------------------------------------------------------ metric definitions


def test_precision_recall_mrr():
    rel = [False, True, False, True]
    assert m.precision_at_k(rel, 2) == 0.5
    assert m.precision_at_k(rel, 4) == 0.5
    assert m.reciprocal_rank(rel) == 0.5
    assert m.reciprocal_rank([False, False]) == 0.0
    assert m.recall_at_k([2, None, 4], 3) == pytest.approx(1 / 3)
    assert m.recall_at_k([2, None, 4], 4) == pytest.approx(2 / 3)


def test_ndcg_matches_hand_computation():
    gains = [0, 1, 1]
    dcg = 1 / math.log2(3) + 1 / math.log2(4)
    idcg = 1 / math.log2(2) + 1 / math.log2(3)
    assert m.ndcg_at_k(gains, 3) == pytest.approx(dcg / idcg)
    assert m.ndcg_at_k([1, 1, 0], 3) == pytest.approx(1.0)
    assert m.ndcg_at_k([0, 0, 0], 3) == 0.0


def test_context_precision_is_rank_aware():
    assert m.context_precision([True, True, False]) == 1.0
    assert m.context_precision([False, True, True]) == pytest.approx((1 / 2 + 2 / 3) / 2)
    assert m.context_precision([False, False]) == 0.0


def test_passage_matching_tolerates_chunk_whitespace():
    chunk = "4 Termination\n\nEither party may terminate this Agreement for convenience upon ninety (90) days"
    assert m.passage_matches("terminate this agreement for convenience upon ninety (90) days", chunk)
    assert not m.passage_matches("annual subscription fee of 48,000 USD", chunk)


def test_dataset_parsing_formats_and_validation():
    csv_data = b"question,relevant_passages,reference_answer\nWhat is the fee?,annual subscription fee of 48000 USD,The fee is 48000 USD.\n"
    [item] = parse_dataset_file("d.csv", csv_data)
    assert item["relevant_passages"] == ["annual subscription fee of 48000 USD"]
    jsonl = (
        b'{"question": "Q1", "relevant_documents": ["msa"]}\n{"question": "Q2", "relevant_passages": ["x"]}'
    )
    assert len(parse_dataset_file("d.jsonl", jsonl)) == 2
    with pytest.raises(Exception) as exc:
        parse_dataset_file("d.json", json.dumps([{"question": "no targets"}]).encode())
    assert "relevant_passages" in str(exc.value.details)  # type: ignore[attr-defined]


# ------------------------------------------------------------------ end-to-end runs

DATASET = {
    "name": "MSA questions",
    "items": [
        {
            "question": "How much notice is needed to terminate for convenience?",
            "relevant_passages": [
                "terminate this Agreement for convenience upon ninety (90) days prior written notice"
            ],
            "reference_answer": "Either party may terminate for convenience upon ninety (90) days prior written notice.",
        },
        {
            "question": "What encryption protects customer data at rest?",
            "relevant_passages": ["encrypt Customer Data at rest using AES-256"],
        },
        {
            "question": "What is the cap on liability?",
            "relevant_passages": ["aggregate liability shall exceed the fees paid in the twelve months"],
        },
    ],
}


def test_evaluation_preset_runs_and_stores_real_metrics(client, admin_session):
    h = auth_headers(admin_session)
    client.post(
        "/api/v1/documents/upload", headers=h, files=[("files", ("msa.md", make_markdown(), "text/markdown"))]
    )
    dataset = client.post("/api/v1/evaluation/datasets", headers=h, json=DATASET).json()
    assert dataset["version"] == 1 and dataset["item_count"] == 3
    again = client.post("/api/v1/evaluation/datasets", headers=h, json=DATASET).json()
    assert again["version"] == 2

    runs = client.post(
        "/api/v1/evaluation/run",
        headers=h,
        json={
            "dataset_id": dataset["id"],
            "name": "Strategies",
            "preset": "retrieval_strategies",
            "generate": True,
        },
    ).json()
    assert len(runs) == 4
    for run in runs:
        detail = client.get(f"/api/v1/evaluation/runs/{run['id']}", headers=h).json()
        assert detail["status"] == "completed", detail["error_message"]
        metrics = detail["metrics"]
        assert metrics["items"] == 3
        assert 0.0 <= metrics["mrr"] <= 1.0
        assert all(
            0.0 <= metrics[k] <= 1.0 for k in ("ndcg@10", "precision@5", "recall@10", "context_precision")
        )
        assert {"precision@1", "recall@5", "ndcg@10", "context_precision", "hit_rate"} <= set(metrics)
        assert len(detail["results"]) == 3
        assert detail["config"]["retrieval"]["strategy"] in {"sparse", "dense", "hybrid"}
        assert detail["dataset_version"] == 1
    hybrid_rerank = client.get(f"/api/v1/evaluation/runs/{runs[3]['id']}", headers=h).json()
    # On this small corpus the reranked hybrid run finds every labelled passage.
    assert hybrid_rerank["metrics"]["recall@5"] == 1.0
    assert hybrid_rerank["metrics"]["faithfulness"] is not None
    assert hybrid_rerank["metrics"]["citation_precision"] is not None

    listing = client.get(f"/api/v1/evaluation/runs?dataset_id={dataset['id']}", headers=h).json()
    assert listing["total"] == 4


def test_evaluation_permissions(client, admin_session):
    h = auth_headers(admin_session)
    dataset = client.post("/api/v1/evaluation/datasets", headers=h, json=DATASET).json()
    token = client.post(
        "/api/v1/admin/invitations", headers=h, json={"email": "r@acme.example.com", "role": "researcher"}
    ).json()["token"]
    researcher = register(client, "r@acme.example.com", org=None, invitation_token=token)
    rh = auth_headers(researcher)
    assert client.get("/api/v1/evaluation/datasets", headers=rh).status_code == 200
    assert (
        client.post("/api/v1/evaluation/run", headers=rh, json={"dataset_id": dataset["id"]}).status_code
        == 403
    )
    outsider = register(client, "eve@globex.example.com", org="Globex")
    assert (
        client.get(f"/api/v1/evaluation/datasets/{dataset['id']}", headers=auth_headers(outsider)).status_code
        == 404
    )
