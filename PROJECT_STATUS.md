# Retrieva — Project Status

_Last updated: 2026-10-23_

This file tracks what is implemented, what is verified, and what is still open. A feature is
listed as **done** only when it is implemented and covered by a passing test or a documented
manual verification.

## Environment notes

| Item | State |
| --- | --- |
| Repository | `origin → https://github.com/RutujaSawant89/Retrieva-.git`, branch `main` |
| Python | 3.12 (uv-managed venv in `backend/.venv`) |
| Node | 22.x |
| Docker | Docker Desktop is installed on the dev machine but fails to start (error dialog on launch). Local development and tests therefore use an **embedded PostgreSQL 16 + pgvector 0.6** (`pgserver`). Docker Compose remains the documented way to run the full stack. |
| GPU | None — all models run on CPU. |

## Architecture decisions

1. **Modular monolith.** One FastAPI service plus Celery workers sharing the same `app` package.
   Service boundaries (`ingestion`, `embeddings`, `retrieval`, `reranking`, `generation`,
   `citations`, `evaluation`) only talk through plain Python interfaces, so any of them can be
   split out later.
2. **Synchronous SQLAlchemy 2 + psycopg 3.** The API and Celery workers share one data-access
   layer. FastAPI runs sync endpoints in its threadpool; streaming uses a generator.
3. **Tenant isolation in two layers.** Every tenant-owned table carries `organization_id`.
   (a) Application queries always filter by the caller's organization; (b) PostgreSQL
   Row-Level Security (`FORCE ROW LEVEL SECURITY`) restricts rows to
   `current_setting('app.current_org')`, which is set per transaction. The API connects as a
   non-superuser role (`retrieva_app`) so RLS cannot be bypassed; migrations run as the owner.
4. **Pluggable providers.** Embeddings (`sentence-transformers` / deterministic hashing for
   tests), rerankers (cross-encoder / lexical), and LLMs (OpenAI-compatible, Anthropic, and an
   offline *extractive* provider) are selected by environment variables.
5. **BM25 implemented in-house** over an analyzer shared with query processing. The index is
   built per organization in memory and invalidated by an index version stamp. This is correct
   and fast for tens of thousands of chunks; the documented scale-out path is a
   database-native BM25 (ParadeDB `pg_search`) or OpenSearch behind the same interface.
6. **Evidence first.** Retrieval returns structured evidence with labelled source IDs
   (`[S1]`…). The generator may only cite those IDs; the verifier independently maps every
   citation to a chunk, checks pages, and scores claim support. Abstention happens before
   generation when evidence is below the relevance threshold, and is flagged after generation
   when coverage is too low.
7. **Honest metrics.** Retrieval scores, rerank scores, citation validity, and evidence
   coverage are reported separately. Nothing is labelled "confidence". Benchmarks are only
   reported from runs that were actually executed (`evaluation/reports/`).

## Phase plan and progress

| Phase | Scope | Status |
| --- | --- | --- |
| 1. Foundation | Backend skeleton, config, DB models, Alembic, RLS, auth (JWT + rotating refresh cookies), RBAC, orgs/invitations, frontend shell + design system + auth pages | in progress |
| 2. Document processing | Upload validation, dedupe, storage, extractors (PDF/DOCX/TXT/MD/CSV/HTML), cleaning, 4 chunkers, embeddings with reuse, pgvector + HNSW, Celery jobs, progress UI | pending |
| 3. Core RAG | Dense, BM25, hybrid, RRF, cross-encoder reranking, query rewriting / multi-query / expansion, compression, context assembly, LLM providers, streaming | pending |
| 4. Evidence & reliability | Citation mapping/validation, page checks, coverage, unsupported-claim detection, abstention, prompt-injection defenses | pending |
| 5. Enterprise | Collections, document/collection permissions, comparison, research mode, export, audit logs, analytics | pending |
| 6. Evaluation | Datasets, IR + RAG metrics, experiment runs, strategy comparison, RAGAS adapter, evaluation dashboard, offline BEIR benchmark | pending |
| 7. Ops | Observability (logs, correlation IDs, OTel, Prometheus, Grafana), Docker, CI, docs, E2E | pending |

## Known limitations

_(Filled in as phases complete.)_
