"""Prometheus metrics. Exposed at ``/metrics`` by the API and on a side port by workers."""

from __future__ import annotations

from prometheus_client import Counter, Histogram

_LATENCY_BUCKETS = (0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30, 60)

HTTP_REQUESTS = Counter("retrieva_http_requests_total", "HTTP requests", ["method", "route", "status"])
HTTP_LATENCY = Histogram(
    "retrieva_http_request_seconds", "HTTP request latency", ["method", "route"], buckets=_LATENCY_BUCKETS
)
RETRIEVAL_LATENCY = Histogram(
    "retrieva_retrieval_seconds", "Retrieval stage latency", ["stage"], buckets=_LATENCY_BUCKETS
)
EMBEDDING_LATENCY = Histogram(
    "retrieva_embedding_seconds", "Embedding batch latency", ["model", "kind"], buckets=_LATENCY_BUCKETS
)
LLM_LATENCY = Histogram(
    "retrieva_llm_seconds", "LLM generation latency", ["provider", "model"], buckets=_LATENCY_BUCKETS
)
LLM_TOKENS = Counter("retrieva_llm_tokens_total", "LLM tokens", ["provider", "model", "kind"])
INGESTION_JOBS = Counter("retrieva_ingestion_jobs_total", "Ingestion job outcomes", ["status"])
CACHE_EVENTS = Counter("retrieva_cache_events_total", "Cache hits and misses", ["cache", "result"])
ABSTENTIONS = Counter("retrieva_abstentions_total", "Answers withheld for insufficient evidence", ["reason"])
