# Retrieva

**Enterprise AI Retrieval & Intelligence Platform**
_Search Smarter. Retrieve Precisely. Trust Every Answer._

Retrieva is an evidence-grounded Retrieval-Augmented Generation platform. It ingests document
collections, retrieves evidence with hybrid search (dense + BM25 + Reciprocal Rank Fusion +
cross-encoder reranking), generates answers that may only cite retrieved passages, and then
independently verifies every citation and claim. It abstains when the evidence is insufficient,
and it measures retrieval quality with a built-in evaluation framework.

> Development is in progress. See [PROJECT_STATUS.md](PROJECT_STATUS.md) for what is
> implemented and verified.

## Repository layout

| Path | Contents |
| --- | --- |
| `backend/` | FastAPI API, SQLAlchemy models, Alembic migrations, RAG services, Celery workers, tests |
| `frontend/` | React 19 + TypeScript + Vite + Tailwind application |
| `PROJECT_STATUS.md` | Architecture decisions, phase progress, known limitations |

## Local development (without Docker)

Requirements: Python 3.12, [uv](https://docs.astral.sh/uv/), Node 22.

```bash
cd backend
uv sync --extra dev --extra ml
uv run python scripts/dev_db.py      # embedded PostgreSQL 16 + pgvector, writes backend/.env
uv run alembic upgrade head
uv run uvicorn app.main:app --reload --port 8000
```

```bash
cd frontend
npm install
npm run dev                           # http://localhost:5173 (proxies /api to :8000)
```

## Tests

```bash
cd backend && uv run pytest
cd frontend && npm test
```
