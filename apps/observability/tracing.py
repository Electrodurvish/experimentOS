"""
OpenTelemetry tracing setup.

Initializes the OTel tracer provider with OTLP exporter.
Every experiment-aware request carries trace context with
experiment_id, variant, and version as span attributes.
"""

import logging
from contextlib import contextmanager

from django.conf import settings

logger = logging.getLogger(__name__)

_tracer = None


def setup_tracing():
    """Initialize OpenTelemetry tracing. Call once at startup."""
    if not getattr(settings, "OTEL_ENABLED", False):
        return

    try:
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor

        resource = Resource.create({
            "service.name": getattr(settings, "OTEL_SERVICE_NAME", "experimentos-api"),
            "service.version": "0.1.0",
        })

        provider = TracerProvider(resource=resource)

        otlp_endpoint = getattr(settings, "OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317")
        exporter = OTLPSpanExporter(endpoint=otlp_endpoint, insecure=True)
        provider.add_span_processor(BatchSpanProcessor(exporter))

        trace.set_tracer_provider(provider)
        logger.info("OpenTelemetry tracing initialized (endpoint: %s)", otlp_endpoint)

    except Exception:
        logger.warning("Failed to initialize OpenTelemetry tracing", exc_info=True)


def instrument_django():
    """Auto-instrument Django requests with OTel spans (only when tracing is enabled)."""
    if not getattr(settings, "OTEL_ENABLED", False):
        return

    try:
        from opentelemetry.instrumentation.django import DjangoInstrumentor

        instrumentor = DjangoInstrumentor()
        if not instrumentor.is_instrumented_by_opentelemetry:
            instrumentor.instrument()
    except Exception:
        logger.warning("Failed to instrument Django with OpenTelemetry", exc_info=True)


@contextmanager
def experiment_span(name, **attributes):
    """
    Start a span carrying experiment attributes. Yields the span (or None when
    OpenTelemetry is unavailable), so callers can add attributes discovered
    inside the block, e.g. the assigned variant.
    """
    tracer = get_tracer()
    if tracer is None:
        yield None
        return

    with tracer.start_as_current_span(name) as span:
        add_experiment_attributes(span, **attributes)
        yield span


def get_tracer(name="experimentos"):
    """Get a named tracer instance."""
    global _tracer
    if _tracer is not None:
        return _tracer

    try:
        from opentelemetry import trace
        _tracer = trace.get_tracer(name)
        return _tracer
    except Exception:
        return None


def add_experiment_attributes(span, experiment_id=None, experiment_key=None,
                               variant=None, version=None, bucket=None):
    """Add experiment context attributes to the current span."""
    if span is None:
        return

    try:
        if experiment_id:
            span.set_attribute("experiment.id", str(experiment_id))
        if experiment_key:
            span.set_attribute("experiment.key", experiment_key)
        if variant:
            span.set_attribute("experiment.variant", variant)
        if version is not None:
            span.set_attribute("experiment.version", version)
        if bucket is not None:
            span.set_attribute("experiment.bucket", bucket)
    except Exception:
        pass
