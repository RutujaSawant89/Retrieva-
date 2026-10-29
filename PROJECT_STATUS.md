# Retrieva — Project Status

_Last updated: 2026-10-29_

A feature is listed as **done** only when it is implemented and covered by a passing automated
test or a documented manual verification.

## Verification summary

| Check | Result |
| --- | --- |
| Backend tests (pytest, real PostgreSQL 16 + pgvector, RLS enforced through a non-superuser role) | 114 passed |
| Frontend unit/component tests (Vitest) | 13 passed |
| End-to-end workflow (Playwright) | Passed locally and in CI |
| Lint / format / typecheck (ruff, oxlint, tsc) | Clean |
| Alembic migrations (upgrade, downgrade, model drift check) | Passed in CI |
| Docker images (backend, frontend) and Compose config | Built and validated in CI; **not run locally** (see environment notes) |
| GitHub Actions CI on `main` | All four jobs green (first run on `49f262b`) |
| Manual verification with real models | BGE embeddings, MS MARCO cross-encoder and Llama 3.2 via Ollama: grounded, cited answers with 100% citation validity; unrelated question abstained; citation → highlighted source passage |

## Environment notes

| Item | State |
| --- | --- |
| Repository | `origin → https://github.com/RutujaSawant89/Retrieva-.git`, branch `main` |
| Python / Node | 3.12 (uv) / 22 |
| Docker | Docker Desktop fails to start on the development machine, so local work used an embedded PostgreSQL 16 + pgvector 0.6 (`pgserver`). The Docker setup is verified by CI builds, not by a local `docker compose up`. |
| Hardware | CPU only; latency figures in reports reflect that. |

## Phases

| Phase | Scope | Status |
| --- | --- | --- |
| 1. Foundation | Modular-monolith backend, config, logging, errors, models, migrations, RLS, auth (Argon2id, JWT + rotating refresh cookies with reuse detection), RBAC, organizations, invitations, frontend shell and design system | Done |
| 2. Document processing | Upload validation, dedupe, storage, extractors (PDF/DOCX/TXT/MD/CSV/HTML), cleaning, four chunkers, embeddings with reuse, pgvector + HNSW, Celery/thread/inline jobs, progress UI | Done |
| 3. Core RAG | Dense, BM25, hybrid, RRF, cross-encoder reranking, rewriting / multi-query / PRF / metadata boost, compression, context assembly, LLM providers, streaming | Done |
| 4. Evidence & reliability | Citation mapping and validation, page checks, coverage, unsupported-claim and missing-figure detection, abstention, prompt-injection defenses | Done |
| 5. Enterprise | Collections, document/collection permissions, comparison, research mode, export, audit logs, analytics | Done |
| 6. Evaluation | Datasets, IR + RAG metrics, experiment presets, run history and comparison, RAGAS adapter, evaluation dashboard, BEIR benchmark | Done (RAGAS adapter untested, see below) |
| 7. Ops | Structured logs, correlation IDs, OpenTelemetry, Prometheus (multiprocess), Grafana dashboard, alerts, Docker, Compose (prod + dev), CI, docs, E2E | Done |

## Measured results

* `evaluation/reports/beir_scifact.md` — BEIR SciFact (5,183 docs, 300 queries): hybrid RRF
  nDCG@10 0.724 vs BM25 0.685 and dense 0.713; the MS MARCO reranker lowers nDCG@10 to 0.700 on
  this dataset.
* `evaluation/reports/northwind_strategies.md` — the four retrieval strategies through the API on
  the 3-document sample corpus (18 questions). The corpus is small, so differences are small.

## Known limitations

* **OCR**: scanned PDFs are detected and reported; an OCR engine plugs into
  `extractors.register_ocr_engine` but none ships by default.
* **Knowledge-graph retrieval** (optional in the specification) is not implemented.
* **RAGAS adapter** is implemented but not exercised by tests (it needs `ragas`, LangChain and a
  paid or local OpenAI-compatible judge). Runs record why RAGAS was skipped instead of writing
  placeholder values.
* **BM25 index** is per-process and in memory; fine up to roughly 10⁵ chunks per organization.
  The scale-out path (ParadeDB `pg_search` / OpenSearch) is described in ARCHITECTURE.md.
* **Verifier** support scoring is heuristic unless `VERIFIER_NLI_MODEL` is configured; it is
  reported as a verification signal, never as confidence.
* **Local LLMs on CPU** are slow for long prompts (Llama 3.2 3B took about 50–145 s per answer
  with eight passages on the development laptop).
* **Accounts**: no email delivery (invitation links are shown to the admin), no SSO or MFA.
* **Model changes**: switching to an embedding model with a different dimension needs a
  migration and reprocessing.
