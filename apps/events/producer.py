import json
import logging
import uuid
from datetime import datetime, timezone

from django.conf import settings

logger = logging.getLogger(__name__)

_producer = None

TOPIC_EXPOSURES = "experiment-exposures"
TOPIC_CONVERSIONS = "conversion-events"


def _get_producer():
    """Lazy singleton Kafka producer."""
    global _producer
    if _producer is not None:
        return _producer

    if not getattr(settings, "KAFKA_ENABLED", False):
        return None

    try:
        from confluent_kafka import Producer

        _producer = Producer({
            "bootstrap.servers": settings.KAFKA_BOOTSTRAP_SERVERS,
            "client.id": "experimentos-api",
            "acks": "all",
            "retries": 3,
            "retry.backoff.ms": 100,
        })
        return _producer
    except Exception:
        logger.warning("Failed to create Kafka producer", exc_info=True)
        return None


def _delivery_callback(err, msg):
    """Called once for each message produced to indicate delivery result."""
    if err is not None:
        logger.warning("Kafka delivery failed: %s", err)


def produce_exposure(
    user_id,
    experiment_id,
    experiment_key,
    version_number,
    variant_key,
    bucket,
    source,
):
    """Produce an experiment exposure event to Kafka. Fire-and-forget."""
    producer = _get_producer()
    if producer is None:
        return

    event = {
        "event_id": str(uuid.uuid4()),
        "event_type": "experiment_exposure",
        "user_id": user_id,
        "experiment_id": str(experiment_id),
        "experiment_key": experiment_key,
        "version_number": version_number,
        "variant_key": variant_key,
        "bucket": bucket,
        "source": source,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    try:
        producer.produce(
            topic=TOPIC_EXPOSURES,
            key=user_id,
            value=json.dumps(event),
            callback=_delivery_callback,
        )
        producer.poll(0)
    except Exception:
        logger.warning("Failed to produce exposure event", exc_info=True)


def produce_conversion(user_id, event_name, value=0.0, metadata=None, event_id=None):
    """Produce a conversion event to Kafka. Fire-and-forget."""
    producer = _get_producer()
    if producer is None:
        return

    event = {
        "event_id": event_id or str(uuid.uuid4()),
        "event_type": event_name,
        "user_id": user_id,
        "event_name": event_name,
        "value": value,
        "metadata": metadata or {},
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    try:
        producer.produce(
            topic=TOPIC_CONVERSIONS,
            key=user_id,
            value=json.dumps(event),
            callback=_delivery_callback,
        )
        producer.poll(0)
    except Exception:
        logger.warning("Failed to produce conversion event", exc_info=True)


def flush_producer(timeout=5.0):
    """Flush pending Kafka messages. Call on shutdown."""
    if _producer is not None:
        _producer.flush(timeout)
