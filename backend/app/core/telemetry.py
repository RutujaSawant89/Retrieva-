"""OpenTelemetry tracing setup (opt-in via ``OTEL_ENABLED``)."""

from __future__ import annotations

import logging
from collections.abc import Iterator
from contextlib import contextmanager

from fastapi import FastAPI
from opentelemetry import trace

from app.core.config import Settings

logger = logging.getLogger(__name__)
tracer = trace.get_tracer("retrieva")


def setup_tracing(app: FastAPI, settings: Settings) -> None:
    if not settings.otel_enabled:
        return
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    provider = TracerProvider(resource=Resource.create({"service.name": settings.otel_service_name}))
    exporter = (
        OTLPSpanExporter(endpoint=settings.otel_exporter_endpoint)
        if settings.otel_exporter_endpoint
        else OTLPSpanExporter()
    )
    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)
    FastAPIInstrumentor.instrument_app(app, excluded_urls="/metrics,/health/live")
    logger.info("otel_tracing_enabled")


@contextmanager
def span(name: str, **attributes: object) -> Iterator[trace.Span]:
    with tracer.start_as_current_span(name) as current:
        for key, value in attributes.items():
            if value is not None:
                current.set_attribute(
                    key, value if isinstance(value, (str, int, float, bool)) else str(value)
                )
        yield current
