# syntax=docker/dockerfile:1.7
# Retrieva API and worker image (same image, different command).

FROM python:3.12-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    HF_HOME=/opt/hf-cache
RUN apt-get update \
 && apt-get install -y --no-install-recommends fonts-dejavu-core libgomp1 curl \
 && rm -rf /var/lib/apt/lists/*
COPY --from=ghcr.io/astral-sh/uv:0.6.11 /uv /usr/local/bin/uv
WORKDIR /app

FROM base AS deps
COPY pyproject.toml uv.lock ./
# CPU-only torch is pinned through the pytorch-cpu index in pyproject.toml.
RUN --mount=type=cache,target=/root/.cache/uv uv sync --frozen --no-dev --extra ml --no-install-project

FROM deps AS models
# Bake the default models into the image so containers start without network access.
ARG PRELOAD_MODELS=true
ARG EMBEDDING_MODEL=BAAI/bge-small-en-v1.5
ARG RERANKER_MODEL=cross-encoder/ms-marco-MiniLM-L-6-v2
RUN if [ "$PRELOAD_MODELS" = "true" ]; then \
      .venv/bin/python -c "from sentence_transformers import SentenceTransformer, CrossEncoder; SentenceTransformer('${EMBEDDING_MODEL}'); CrossEncoder('${RERANKER_MODEL}')"; \
    else mkdir -p /opt/hf-cache; fi

FROM base AS runtime
RUN groupadd --system retrieva && useradd --system --gid retrieva --home /app retrieva
COPY --from=deps /app/.venv /app/.venv
COPY --from=models /opt/hf-cache /opt/hf-cache
COPY app ./app
COPY alembic ./alembic
COPY alembic.ini ./
COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh \
 && mkdir -p /data/storage \
 && chown -R retrieva:retrieva /data /opt/hf-cache
ENV PATH="/app/.venv/bin:$PATH" \
    STORAGE_DIR=/data/storage \
    HF_HUB_DISABLE_TELEMETRY=1
USER retrieva
EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=5s --start-period=60s --retries=5 \
  CMD curl -fsS http://localhost:8000/health/live || exit 1
ENTRYPOINT ["docker-entrypoint.sh"]
CMD ["api"]
