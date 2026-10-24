# Retrieva

**Enterprise AI Retrieval & Intelligence Platform**
_Search Smarter. Retrieve Precisely. Trust Every Answer._

[![CI](https://github.com/RutujaSawant89/Retrieva-/actions/workflows/ci.yml/badge.svg)](https://github.com/RutujaSawant89/Retrieva-/actions/workflows/ci.yml)

Retrieva is an evidence-grounded Retrieval-Augmented Generation platform. It ingests document
collections, retrieves evidence with hybrid search, generates answers that may only cite the
retrieved passages, and then **independently verifies** every citation and claim. When the
evidence is insufficient it abstains instead of guessing, and its retrieval quality is measured
with a built-in evaluation framework rather than asserted.

For every answer Retrieva shows:

1. **Where** the information came from — document, page, section, and the exact passage, one
   click away in the highlighted source text.
2. **Why** each passage was retrieved — its dense, BM25, fusion and reranker scores and ranks.
3. **Which** passages support which sentences — claim-level verification.
4. **Whether** the answer is supported — citation validity, citation precision and evidence
   coverage, with unsupported claims, fabricated citations and figures missing from the
   sources flagged.
5. **When** it declined to answer — and the closest passages it found.
6. **How** quality changes across configurations — measured experiments, not claims.

## Measured results

From [`evaluation/reports/beir_scifact.md`](evaluation/reports/beir_scifact.md): BEIR SciFact,
5,183 abstracts, 300 test queries with official relevance judgments, CPU only, using Retrieva's
own BM25, embedding, fusion and reranking components.

| Configuration | nDCG@10 | Recall@100 | MRR@10 |
| --- | ---: | ---: | ---: |
| BM25 (in-house implementation) | 0.685 | 0.918 | 0.646 |
| Dense (`bge-small-en-v1.5`) | 0.713 | 0.942 | 0.682 |
| **Hybrid (RRF, k = 60)** | **0.724** | **0.972** | **0.689** |
| Hybrid + MS MARCO cross-encoder (top 30) | 0.700 | 0.972 | 0.667 |

Hybrid fusion beats either retriever alone. The general-purpose web-search reranker *hurts* on
scientific claims, which is exactly why every pipeline stage in Retrieva is a toggle that you
validate on your own corpus with the evaluation framework. A second report,
[`northwind_strategies.md`](evaluation/reports/northwind_strategies.md), runs the same comparison
end-to-end through the API on a small sample corpus.

## Features

| Area | What's there |
| --- | --- |
| Documents | PDF, DOCX, TXT, Markdown, CSV, HTML · drag-and-drop multi-upload with progress · validation, size limits, duplicate detection · live processing status · preview, chunks, pipeline timings, reprocessing with other chunking settings |
| Ingestion | Page-, heading- and table-preserving extraction · cleaning (running headers/footers, de-hyphenation) · recursive, token, semantic and structure-aware chunking with exact offsets · batched embeddings with reuse for unchanged content · Celery workers |
| Retrieval | pgvector dense search (cosine / inner product, HNSW) · in-house BM25 · Reciprocal Rank Fusion · cross-encoder reranking · follow-up rewriting, multi-query, pseudo-relevance feedback, metadata boosting — each gated and recorded · dedupe · contextual compression · scoped to documents or collections |
| Generation | OpenAI-compatible (incl. Ollama/vLLM), Anthropic, or LLM-free extractive mode · streaming (SSE) · labelled source envelopes · cite-or-abstain prompting · conflict and prompt-injection detection · conversation memory with summaries |
| Verification | Claim extraction · citation-to-chunk mapping · fabricated-label, missing-figure and page-reference checks · support scoring (lexical + embedding, optional NLI) · abstention before and after generation |
| Workspace | Chat with evidence panel and history · search explorer · multi-step research reports · document comparison (changes, additions, figure contradictions) · collections · PDF/DOCX/Markdown export with citations |
| Evaluation | Versioned datasets · experiment presets · Precision/Recall@K, MRR, nDCG, context precision/recall, faithfulness, answer relevancy, citation precision/coverage · run history and comparison · optional RAGAS |
| Enterprise | Organizations · admin/analyst/researcher/viewer roles · invitations · private documents and collections · PostgreSQL Row-Level Security · rate limits · audit log · analytics computed from real usage |
| Operations | Structured logs with correlation IDs · Prometheus metrics · OpenTelemetry traces · Grafana dashboard and alerts · Docker Compose · GitHub Actions CI |

## Architecture

A modular monolith: one FastAPI service and one Celery worker image over PostgreSQL 16 +
pgvector and Redis, with a React 19 + TypeScript SPA. See [ARCHITECTURE.md](ARCHITECTURE.md) for
diagrams and design decisions, and [SECURITY.md](SECURITY.md) for the security model.

```
backend/      FastAPI app, services (ingestion, embeddings, retrieval, reranking, generation,
              citations, evaluation), Celery workers, Alembic migrations, tests
frontend/     React 19 + Vite + Tailwind + TanStack Query + Recharts, Vitest + Playwright
evaluation/   sample corpus, labelled datasets, benchmark scripts, measured reports
infrastructure/  Postgres role init, Prometheus, Grafana, alert rules
docs/         deployment and evaluation guides
```

## Quick start

### Docker Compose

```bash
cp .env.example .env        # set POSTGRES_PASSWORD, APP_DB_PASSWORD, JWT_SECRET, GRAFANA_ADMIN_PASSWORD
docker compose up -d --build
# http://localhost:8080
```

Add `--profile monitoring` for Prometheus, Grafana and Jaeger. To generate answers with an LLM
instead of extractive mode, set `LLM_PROVIDER`, `LLM_MODEL` and `LLM_API_KEY` / `LLM_BASE_URL`
(see [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md)).

### Without Docker

Requirements: Python 3.12, [uv](https://docs.astral.sh/uv/), Node 22.

```bash
cd backend
uv sync --extra dev --extra ml
uv run python scripts/dev_db.py      # embedded PostgreSQL 16 + pgvector; writes backend/.env
uv run alembic upgrade head
echo "INGESTION_MODE=thread" >> .env
uv run uvicorn app.main:app --port 8000
```

```bash
cd frontend
npm install
npm run dev                          # http://localhost:5173
```

### Try it with sample data

Upload the three documents in `evaluation/datasets/sample_corpus/`, ask "How much notice is
needed to terminate the agreement for convenience?", then open the Evaluation page, upload
`evaluation/datasets/northwind-qa.json` and run the "BM25 vs dense vs hybrid vs hybrid + rerank"
experiment.

## Tests

```bash
cd backend && uv run pytest          # 99 tests on real PostgreSQL + pgvector, RLS enforced
cd frontend && npm test              # Vitest unit and component tests
cd frontend && npm run test:e2e      # Playwright: register → upload → ask → verify → open source
```

CI runs linting, all three suites, migration round-trips and both Docker image builds on every
push.

## Documentation

* [ARCHITECTURE.md](ARCHITECTURE.md) — system design, retrieval engine, verification, data model, scaling limits
* [SECURITY.md](SECURITY.md) — threat model and controls
* [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) — Compose, local setup, configuration reference, operations
* [docs/EVALUATION.md](docs/EVALUATION.md) — metrics, datasets, experiments, benchmarks
* [PROJECT_STATUS.md](PROJECT_STATUS.md) — what is implemented and verified, and known limitations
* API reference: `/api/docs` (OpenAPI) on a running instance
