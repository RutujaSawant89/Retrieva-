# Deployment and operations

## Option A — Docker Compose (recommended)

Requirements: Docker 24+ with Compose v2, ~4 GB RAM (the API and worker each load the embedding
and reranking models, about 250 MB together).

```bash
cp .env.example .env
# edit .env: set POSTGRES_PASSWORD, APP_DB_PASSWORD, JWT_SECRET, GRAFANA_ADMIN_PASSWORD
docker compose up -d --build
```

Open <http://localhost:8080> and create an organization. The first build downloads the CPU
build of PyTorch and bakes the default models into the image (several minutes).

| Service | Purpose |
| --- | --- |
| `postgres` | PostgreSQL 16 + pgvector. `init-app-role.sh` creates the non-superuser runtime role on first start |
| `redis` | Celery broker, query-embedding cache, shared rate limits |
| `migrate` | Runs `alembic upgrade head` as the schema owner, then exits |
| `api` | FastAPI (2 uvicorn workers by default, `API_WORKERS`) |
| `worker` | Celery worker for the `ingestion` and `evaluation` queues (`WORKER_CONCURRENCY`) |
| `web` | nginx serving the SPA and proxying `/api` on the same origin (needed for the `SameSite=Strict` refresh cookie) |

Monitoring (Prometheus :9090, Grafana :3000, Jaeger :16686):

```bash
docker compose --profile monitoring up -d
```

Set `OTEL_ENABLED=true` and `OTEL_EXPORTER_ENDPOINT=http://jaeger:4318/v1/traces` to send traces.

### Using an LLM

By default `LLM_PROVIDER=extractive`: answers consist of verbatim, cited evidence sentences and
no model is called. To generate answers:

```bash
# OpenAI
LLM_PROVIDER=openai
LLM_MODEL=gpt-4o-mini
LLM_API_KEY=sk-...

# Local Ollama on the Docker host
LLM_PROVIDER=openai
LLM_MODEL=llama3.2
LLM_BASE_URL=http://host.docker.internal:11434/v1

# Anthropic
LLM_PROVIDER=anthropic
LLM_MODEL=claude-sonnet-5-5
LLM_API_KEY=...
```

CPU-only local models are slow on long prompts (a 3B model can take over a minute to process
eight passages); lower the retrieval `top_k` or use a GPU / hosted model for interactive use.

### Development with Docker

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build
cd frontend && npm install && npm run dev      # http://localhost:5173
```

## Option B — local processes (no Docker)

Requirements: Python 3.12, [uv](https://docs.astral.sh/uv/), Node 22.

```bash
cd backend
uv sync --extra dev --extra ml
uv run python scripts/dev_db.py        # embedded PostgreSQL 16 + pgvector; writes backend/.env
uv run alembic upgrade head
echo "INGESTION_MODE=thread" >> .env   # no Redis/Celery needed
uv run uvicorn app.main:app --port 8000
```

```bash
cd frontend
npm install
npm run dev                            # http://localhost:5173
```

`scripts/dev_db.py` creates both the owner role (used by Alembic) and the non-superuser
`retrieva_app` role (used by the API), so Row-Level Security is enforced locally too.

## Configuration reference

All settings are environment variables (see `backend/app/core/config.py`):

| Variable | Default | Notes |
| --- | --- | --- |
| `DATABASE_URL` | — | Runtime role (non-superuser, no BYPASSRLS) |
| `MIGRATION_DATABASE_URL` | `DATABASE_URL` | Schema owner, for Alembic |
| `REDIS_URL` | `redis://localhost:6379/0` | Empty disables Redis (in-process fallbacks) |
| `INGESTION_MODE` | `celery` | `celery`, `thread` or `inline` |
| `JWT_SECRET` | dev value | Must be ≥ 32 chars in production |
| `ACCESS_TOKEN_TTL_MINUTES` / `REFRESH_TOKEN_TTL_DAYS` | 15 / 14 | |
| `COOKIE_SECURE` | `false` | Must be `true` in production |
| `RATE_LIMIT_PER_MINUTE` / `AUTH_RATE_LIMIT_PER_MINUTE` | 120 / 10 | Per user / per IP |
| `MAX_UPLOAD_MB` | 50 | |
| `EMBEDDING_PROVIDER` | `sentence-transformers` | `hashing` is for tests only |
| `EMBEDDING_MODEL` / `EMBEDDING_DIM` | `BAAI/bge-small-en-v1.5` / 384 | Dimension change needs a migration |
| `CHUNKING_STRATEGY`, `CHUNK_SIZE`, `CHUNK_OVERLAP`, `CHUNK_MAX_TOKENS` | `structure`, 900, 150, 256 | Defaults for new uploads |
| `RERANKER_PROVIDER` / `RERANKER_MODEL` | `cross-encoder` / `cross-encoder/ms-marco-MiniLM-L-6-v2` | `lexical` or `none` also accepted |
| `RERANK_ABSTAIN_THRESHOLD` | -4.0 | Cross-encoder logit below which the system abstains |
| `LLM_PROVIDER`, `LLM_MODEL`, `LLM_API_KEY`, `LLM_BASE_URL` | `extractive` | See above |
| `LLM_TIMEOUT_SECONDS` | 180 | Per streamed chunk |
| `CONTEXT_TOKEN_BUDGET` | 2400 | Evidence tokens passed to the LLM |
| `VERIFIER_NLI_MODEL` | empty | e.g. `cross-encoder/nli-deberta-v3-xsmall` for NLI-based support scoring |
| `HF_OFFLINE` | `false` | Use only locally cached models |
| `OTEL_ENABLED`, `OTEL_EXPORTER_ENDPOINT` | `false` | OTLP/HTTP traces |

## Operations

* **Migrations**: `docker compose run --rm migrate` (or `uv run alembic upgrade head`).
* **Backups**: back up the `pgdata` volume (or use `pg_dump`) and the `storage` volume together;
  extracted text and original files live in `storage`.
* **Changing the embedding model**: set the new model and dimension, add a migration altering
  `document_chunks.embedding`, deploy, then reprocess documents. Vectors carry their model
  version, so mixed states never mix vector spaces.
* **Health**: `/health/live` (process), `/health/ready` (database + Redis).
* **Scaling**: API replicas are stateless apart from per-process caches (BM25 index, query
  embeddings) that rebuild automatically. Scale workers for ingestion throughput.
