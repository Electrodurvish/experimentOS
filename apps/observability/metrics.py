"""
Prometheus metrics for ExperimentOS.

Tracks:
- HTTP request latency and count (by method, endpoint, status)
- Experiment evaluation latency and count (by experiment key)
- Assignment counts (by experiment, variant)
- Cache hit/miss rates
- Event producer / consumer counts
- Error counts
"""

import logging

logger = logging.getLogger(__name__)

_metrics_initialized = False

# Metric instances (lazy initialized)
REQUEST_LATENCY = None
REQUEST_COUNT = None
EVALUATION_LATENCY = None
EVALUATION_COUNT = None
ASSIGNMENT_COUNT = None
CACHE_HIT_COUNT = None
CACHE_MISS_COUNT = None
EVENT_PRODUCED_COUNT = None
EVENT_CONSUMED_COUNT = None
ERROR_COUNT = None
BEAT_HEARTBEAT = None
DECISION_SWEEP = None


def _init_metrics():
    """Initialize Prometheus metrics. Called once."""
    global _metrics_initialized
    global REQUEST_LATENCY, REQUEST_COUNT
    global EVALUATION_LATENCY, EVALUATION_COUNT, ASSIGNMENT_COUNT
    global CACHE_HIT_COUNT, CACHE_MISS_COUNT
    global EVENT_PRODUCED_COUNT, EVENT_CONSUMED_COUNT, ERROR_COUNT
    global BEAT_HEARTBEAT, DECISION_SWEEP

    if _metrics_initialized:
        return

    try:
        from prometheus_client import Counter, Gauge, Histogram

        REQUEST_LATENCY = Histogram(
            "http_request_duration_seconds",
            "HTTP request latency",
            ["method", "endpoint", "status"],
            buckets=[0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5],
        )

        REQUEST_COUNT = Counter(
            "http_requests_total",
            "Total HTTP requests",
            ["method", "endpoint", "status"],
        )

        EVALUATION_LATENCY = Histogram(
            "experiment_evaluation_duration_seconds",
            "Experiment evaluation latency",
            ["experiment_key"],
            buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1],
        )

        EVALUATION_COUNT = Counter(
            "experiment_evaluations_total",
            "Total experiment evaluations",
            ["experiment_key", "result"],
        )

        ASSIGNMENT_COUNT = Counter(
            "experiment_assignments_total",
            "Total experiment assignments",
            ["experiment_key", "variant_key"],
        )

        CACHE_HIT_COUNT = Counter(
            "experiment_cache_hits_total",
            "Experiment config cache hits",
        )

        CACHE_MISS_COUNT = Counter(
            "experiment_cache_misses_total",
            "Experiment config cache misses",
        )

        EVENT_PRODUCED_COUNT = Counter(
            "events_produced_total",
            "Total events produced to Kafka",
            ["topic"],
        )

        EVENT_CONSUMED_COUNT = Counter(
            "events_consumed_total",
            "Total events consumed from Kafka",
            ["topic", "result"],
        )

        ERROR_COUNT = Counter(
            "errors_total",
            "Total errors",
            ["component", "error_type"],
        )

        BEAT_HEARTBEAT = Gauge(
            "celery_beat_last_heartbeat_timestamp_seconds",
            "Unix time of the last Celery beat heartbeat task",
            multiprocess_mode="max",
        )

        DECISION_SWEEP = Gauge(
            "decision_sweep_last_success_timestamp_seconds",
            "Unix time of the last completed decision engine sweep",
            multiprocess_mode="max",
        )

        _metrics_initialized = True
        logger.info("Prometheus metrics initialized")

    except Exception:
        logger.warning("Failed to initialize Prometheus metrics", exc_info=True)


def record_request(method, endpoint, status_code, duration):
    """Record an HTTP request metric."""
    _init_metrics()
    if REQUEST_LATENCY:
        REQUEST_LATENCY.labels(method=method, endpoint=endpoint, status=str(status_code)).observe(duration)
    if REQUEST_COUNT:
        REQUEST_COUNT.labels(method=method, endpoint=endpoint, status=str(status_code)).inc()


def record_evaluation(experiment_key, result, duration):
    """Record an experiment evaluation metric."""
    _init_metrics()
    if EVALUATION_LATENCY:
        EVALUATION_LATENCY.labels(experiment_key=experiment_key).observe(duration)
    if EVALUATION_COUNT:
        EVALUATION_COUNT.labels(experiment_key=experiment_key, result=result).inc()


def record_assignment(experiment_key, variant_key):
    """Record an experiment assignment metric."""
    _init_metrics()
    if ASSIGNMENT_COUNT:
        ASSIGNMENT_COUNT.labels(experiment_key=experiment_key, variant_key=variant_key).inc()


def record_cache_hit():
    """Record a cache hit."""
    _init_metrics()
    if CACHE_HIT_COUNT:
        CACHE_HIT_COUNT.inc()


def record_cache_miss():
    """Record a cache miss."""
    _init_metrics()
    if CACHE_MISS_COUNT:
        CACHE_MISS_COUNT.inc()


def record_event_produced(topic):
    """Record an event produced to Kafka."""
    _init_metrics()
    if EVENT_PRODUCED_COUNT:
        EVENT_PRODUCED_COUNT.labels(topic=topic).inc()


def record_event_consumed(topic, result):
    """Record a consumed event. result is one of processed, duplicate, invalid."""
    _init_metrics()
    if EVENT_CONSUMED_COUNT:
        EVENT_CONSUMED_COUNT.labels(topic=topic, result=result).inc()


def record_error(component, error_type):
    """Record an error."""
    _init_metrics()
    if ERROR_COUNT:
        ERROR_COUNT.labels(component=component, error_type=error_type).inc()


def refresh_job_gauges():
    """Copy background-job heartbeats (written to Redis by Celery tasks) into gauges at scrape time."""
    _init_metrics()
    try:
        from apps.decisions.tasks import BEAT_HEARTBEAT_KEY, DECISION_SWEEP_KEY
        from apps.engine.cache import get_redis_client

        client = get_redis_client()
        for gauge, key in ((BEAT_HEARTBEAT, BEAT_HEARTBEAT_KEY), (DECISION_SWEEP, DECISION_SWEEP_KEY)):
            value = client.get(key)
            if gauge is not None and value:
                gauge.set(float(value))
    except Exception:
        logger.debug("Could not refresh job gauges", exc_info=True)


def metrics_registry():
    """
    The registry to expose. With several gunicorn workers each process has its own
    counters, so when PROMETHEUS_MULTIPROC_DIR is set the per-process files are
    aggregated (see gunicorn.conf.py for the matching child_exit hook).
    """
    import os

    from prometheus_client import REGISTRY, CollectorRegistry, multiprocess

    if os.environ.get("PROMETHEUS_MULTIPROC_DIR"):
        registry = CollectorRegistry()
        multiprocess.MultiProcessCollector(registry)
        return registry
    return REGISTRY
