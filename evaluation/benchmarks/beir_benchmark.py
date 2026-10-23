"""Offline retrieval benchmark on a public BEIR dataset (default: SciFact).

Runs Retrieva's own retrieval components in-process — the BM25 implementation, the embedding
model, Reciprocal Rank Fusion and the cross-encoder reranker — on a dataset with published
relevance judgments, so results are reproducible and comparable with the literature.

Usage (from the repository root)::

    cd backend
    uv run python ../evaluation/benchmarks/beir_benchmark.py --dataset scifact

Outputs ``evaluation/reports/beir_<dataset>.json`` and ``.md``. Downloads the dataset from the
Hugging Face Hub (``BeIR/<dataset>`` and ``BeIR/<dataset>-qrels``) into
``evaluation/datasets/cache`` on first run (needs ``uv sync --extra bench``).
"""

from __future__ import annotations

import argparse
import csv
import json
import platform
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.services.evaluation import metrics as m  # noqa: E402
from app.services.retrieval.bm25 import BM25Index  # noqa: E402
from app.services.retrieval.fusion import reciprocal_rank_fusion  # noqa: E402

CACHE = ROOT / "evaluation" / "datasets" / "cache"
REPORTS = ROOT / "evaluation" / "reports"


def load_beir(name: str) -> tuple[dict[str, str], dict[str, str], dict[str, dict[str, int]]]:
    from huggingface_hub import hf_hub_download

    import pyarrow.parquet as pq

    def table(filename: str) -> list[dict]:
        path = hf_hub_download(f"BeIR/{name}", filename, repo_type="dataset", cache_dir=CACHE)
        return pq.read_table(path).to_pylist()

    corpus = {
        str(doc["_id"]): f"{doc.get('title') or ''}\n{doc.get('text') or ''}".strip()
        for doc in table("corpus/corpus-00000-of-00001.parquet")
    }
    queries = {str(q["_id"]): q["text"] for q in table("queries/queries-00000-of-00001.parquet")}
    qrels_path = hf_hub_download(f"BeIR/{name}-qrels", "test.tsv", repo_type="dataset", cache_dir=CACHE)
    qrels: dict[str, dict[str, int]] = {}
    with open(qrels_path, encoding="utf-8") as handle:
        for row in csv.DictReader(handle, delimiter="\t"):
            if int(row["score"]) > 0:
                qrels.setdefault(row["query-id"], {})[row["corpus-id"]] = int(row["score"])
    queries = {qid: text for qid, text in queries.items() if qid in qrels}
    return corpus, queries, qrels


def evaluate(rankings: dict[str, list[str]], qrels: dict[str, dict[str, int]]) -> dict[str, float]:
    ndcg, recall100, mrr10, p1 = [], [], [], []
    for qid, ranked in rankings.items():
        rel = qrels[qid]
        gains = [float(rel.get(doc, 0)) for doc in ranked]
        ideal = sorted(rel.values(), reverse=True)
        ndcg.append(m.ndcg_at_k(gains, 10, ideal_gains=ideal))
        found = [next((i for i, d in enumerate(ranked, 1) if d == target), None) for target in rel]
        recall100.append(m.recall_at_k(found, 100))
        mrr10.append(m.reciprocal_rank([doc in rel for doc in ranked[:10]]))
        p1.append(m.precision_at_k([doc in rel for doc in ranked], 1))
    return {
        "ndcg@10": round(float(np.mean(ndcg)), 4),
        "recall@100": round(float(np.mean(recall100)), 4),
        "mrr@10": round(float(np.mean(mrr10)), 4),
        "p@1": round(float(np.mean(p1)), 4),
    }


def latency_summary(samples: list[float]) -> dict[str, float]:
    return {
        "mean_ms": round(float(np.mean(samples)), 2),
        "p95_ms": round(float(np.percentile(samples, 95)), 2),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", default="scifact")
    parser.add_argument("--embedding-model", default="BAAI/bge-small-en-v1.5")
    parser.add_argument("--reranker", default="cross-encoder/ms-marco-MiniLM-L-6-v2")
    parser.add_argument("--rerank-depth", type=int, default=30)
    parser.add_argument("--max-queries", type=int, default=0, help="limit queries (0 = all)")
    args = parser.parse_args()

    print(f"Loading BEIR/{args.dataset} …", flush=True)
    corpus, queries, qrels = load_beir(args.dataset)
    if args.max_queries:
        queries = dict(list(queries.items())[: args.max_queries])
    doc_ids = list(corpus)
    texts = [corpus[d] for d in doc_ids]
    print(f"{len(doc_ids)} documents, {len(queries)} queries", flush=True)

    results: dict[str, dict] = {}
    rankings: dict[str, dict[str, list[str]]] = {}

    # BM25 ----------------------------------------------------------------------------------
    began = time.perf_counter()
    bm25 = BM25Index(doc_ids, texts)
    bm25_build = time.perf_counter() - began
    rankings["bm25"], lat = {}, []
    for qid, q in queries.items():
        t = time.perf_counter()
        rankings["bm25"][qid] = [d for d, _ in bm25.search(q, top_k=100)]
        lat.append((time.perf_counter() - t) * 1000)
    results["BM25"] = {**evaluate(rankings["bm25"], qrels), **latency_summary(lat)}
    print("BM25", results["BM25"], flush=True)

    # Dense ---------------------------------------------------------------------------------
    from sentence_transformers import CrossEncoder, SentenceTransformer

    model = SentenceTransformer(args.embedding_model, device="cpu")
    prefix = (
        "Represent this sentence for searching relevant passages: "
        if "bge" in args.embedding_model.lower()
        else ""
    )
    began = time.perf_counter()
    doc_vectors = model.encode(texts, batch_size=32, normalize_embeddings=True, show_progress_bar=True)
    embed_seconds = time.perf_counter() - began
    rankings["dense"], lat = {}, []
    for qid, q in queries.items():
        t = time.perf_counter()
        qv = model.encode([prefix + q], normalize_embeddings=True)[0]
        top = np.argsort(-(doc_vectors @ qv))[:100]
        rankings["dense"][qid] = [doc_ids[i] for i in top]
        lat.append((time.perf_counter() - t) * 1000)
    results["Dense"] = {**evaluate(rankings["dense"], qrels), **latency_summary(lat)}
    print("Dense", results["Dense"], flush=True)

    # Hybrid (RRF) ---------------------------------------------------------------------------
    rankings["hybrid"] = {}
    for qid in queries:
        fused = reciprocal_rank_fusion({"dense": rankings["dense"][qid], "bm25": rankings["bm25"][qid]}, k=60)
        rankings["hybrid"][qid] = [d for d, _ in fused][:100]
    hybrid_lat = [
        a + b
        for a, b in zip(
            [results["BM25"]["mean_ms"]] * len(queries),
            [results["Dense"]["mean_ms"]] * len(queries),
            strict=True,
        )
    ]
    results["Hybrid (RRF k=60)"] = {
        **evaluate(rankings["hybrid"], qrels),
        "mean_ms": round(hybrid_lat[0], 2),
        "p95_ms": None,
    }
    print("Hybrid", results["Hybrid (RRF k=60)"], flush=True)

    # Hybrid + cross-encoder rerank ------------------------------------------------------------
    reranker = CrossEncoder(args.reranker, device="cpu")
    rankings["rerank"], lat = {}, []
    for qid, q in queries.items():
        candidates = rankings["hybrid"][qid][: args.rerank_depth]
        t = time.perf_counter()
        scores = reranker.predict([(q, corpus[d]) for d in candidates], show_progress_bar=False)
        lat.append((time.perf_counter() - t) * 1000)
        reranked = [candidates[i] for i in np.argsort(-np.asarray(scores))]
        rankings["rerank"][qid] = reranked + rankings["hybrid"][qid][args.rerank_depth :]
    results[f"Hybrid + rerank (top {args.rerank_depth})"] = {
        **evaluate(rankings["rerank"], qrels),
        "rerank_mean_ms": latency_summary(lat)["mean_ms"],
        "rerank_p95_ms": latency_summary(lat)["p95_ms"],
    }
    print("Rerank", results[f"Hybrid + rerank (top {args.rerank_depth})"], flush=True)

    report = {
        "dataset": f"BEIR/{args.dataset}",
        "split": "test",
        "documents": len(doc_ids),
        "queries": len(queries),
        "embedding_model": args.embedding_model,
        "reranker": args.reranker,
        "rerank_depth": args.rerank_depth,
        "bm25_index_seconds": round(bm25_build, 2),
        "embedding_seconds": round(embed_seconds, 1),
        "environment": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "device": "cpu",
        },
        "date": datetime.now(UTC).isoformat(timespec="seconds"),
        "results": results,
    }
    REPORTS.mkdir(parents=True, exist_ok=True)
    stem = REPORTS / f"beir_{args.dataset}"
    stem.with_suffix(".json").write_text(json.dumps(report, indent=2), encoding="utf-8")

    lines = [
        f"# BEIR/{args.dataset} retrieval benchmark",
        "",
        f"Run {report['date']} on {report['environment']['platform']} (CPU). "
        f"{report['documents']} documents, {report['queries']} test queries with official relevance judgments.",
        "",
        f"Embedding model `{args.embedding_model}` · reranker `{args.reranker}` (top {args.rerank_depth}) · "
        f"BM25 k1=1.2, b=0.75 · RRF k=60.",
        "",
        "| Configuration | nDCG@10 | Recall@100 | MRR@10 | P@1 | Query latency (mean) |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for name, r in results.items():
        latency = r.get("mean_ms") or r.get("rerank_mean_ms")
        suffix = " (+ rerank)" if "rerank_mean_ms" in r else ""
        lines.append(
            f"| {name} | {r['ndcg@10']:.4f} | {r['recall@100']:.4f} | {r['mrr@10']:.4f} | {r['p@1']:.4f} | "
            f"{latency:.1f} ms{suffix} |"
        )
    lines += [
        "",
        "Latency is per query on CPU and excludes network and database overhead; hybrid latency is the sum of "
        "its BM25 and dense components. Indexing: BM25 "
        f"{report['bm25_index_seconds']} s, embeddings {report['embedding_seconds']} s.",
        "",
        "Reproduce: `cd backend && uv run python ../evaluation/benchmarks/beir_benchmark.py --dataset "
        f"{args.dataset}`",
    ]
    stem.with_suffix(".md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Wrote {stem}.json and .md", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
