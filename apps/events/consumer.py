"""
Kafka → ClickHouse event consumer.

Delivery semantics: at-least-once from Kafka, made idempotent with a Redis
SETNX key per event_id.

- Offsets are committed only after an event is stored (or deliberately skipped),
  so a crash between poll and insert re-delivers the event instead of losing it.
- If the ClickHouse insert fails, the dedup key is released and the partition is
  rewound to the failed offset, so the retry is not mistaken for a duplicate.
  Retries back off exponentially up to MAX_BACKOFF_SECONDS.
"""

import json
import logging
import signal
import time

from django.conf import settings

from apps.engine.cache import get_redis_client
from apps.events.clickhouse import insert_conversion, insert_exposure
from apps.events.producer import TOPIC_CONVERSIONS, TOPIC_EXPOSURES
from apps.observability.metrics import record_error, record_event_consumed

logger = logging.getLogger(__name__)

MAX_BACKOFF_SECONDS = 30.0


def _dedup_key(event_id):
    return f"dedup:{event_id}"


def is_duplicate(event_id):
    """
    Check if an event has already been processed using Redis SETNX.
    Returns True if duplicate (already processed), False if new.
    """
    try:
        client = get_redis_client()
        ttl = getattr(settings, "EVENT_DEDUP_TTL", 86400)
        # SET NX returns True if key was set (new event), False if exists (duplicate)
        was_set = client.set(_dedup_key(event_id), "1", nx=True, ex=ttl)
        return not was_set
    except Exception:
        logger.warning("Redis dedup check failed, processing event anyway", exc_info=True)
        return False


def release_dedup(event_id):
    """Forget an event_id so a failed event can be retried."""
    try:
        get_redis_client().delete(_dedup_key(event_id))
    except Exception:
        logger.warning("Failed to release dedup key for %s", event_id, exc_info=True)


def _process(event, topic, insert, kind):
    event_id = event.get("event_id")
    if not event_id:
        logger.warning("%s event missing event_id, skipping", kind.title())
        record_event_consumed(topic, "invalid")
        return

    if is_duplicate(event_id):
        logger.debug("Duplicate %s event %s, skipping", kind, event_id)
        record_event_consumed(topic, "duplicate")
        return

    try:
        insert(event)
    except Exception:
        release_dedup(event_id)
        record_event_consumed(topic, "failed")
        raise

    record_event_consumed(topic, "processed")
    logger.debug("Processed %s event %s", kind, event_id)


def process_exposure(event):
    """Deduplicate and store an exposure event. Raises EventStoreError if it must be retried."""
    _process(event, TOPIC_EXPOSURES, insert_exposure, "exposure")


def process_conversion(event):
    """Deduplicate and store a conversion event. Raises EventStoreError if it must be retried."""
    _process(event, TOPIC_CONVERSIONS, insert_conversion, "conversion")


PROCESSORS = {
    TOPIC_EXPOSURES: process_exposure,
    TOPIC_CONVERSIONS: process_conversion,
}


def handle_message(consumer, msg):
    """
    Process one Kafka message and commit its offset, or rewind for retry.
    Returns True when the offset was committed, False when it will be retried.
    """
    from confluent_kafka import TopicPartition

    topic = msg.topic()
    processor = PROCESSORS.get(topic)
    if processor is None:
        logger.warning("Received message from unexpected topic: %s", topic)
        consumer.commit(message=msg, asynchronous=True)
        return True

    try:
        event = json.loads(msg.value().decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        # Poison message: retrying cannot help, so skip it.
        logger.warning("Failed to decode message from topic %s at offset %s", topic, msg.offset())
        record_event_consumed(topic, "invalid")
        consumer.commit(message=msg, asynchronous=True)
        return True

    try:
        processor(event)
    except Exception:
        logger.warning("Failed to store event from %s at offset %s; will retry", topic, msg.offset(),
                       exc_info=True)
        record_error("event_consumer", "store_failed")
        consumer.seek(TopicPartition(topic, msg.partition(), msg.offset()))
        return False

    consumer.commit(message=msg, asynchronous=True)
    return True


def run_consumer():
    """
    Main consumer loop. Subscribes to exposure and conversion topics,
    processes messages with deduplication, and inserts into ClickHouse.
    """
    from confluent_kafka import Consumer, KafkaError

    running = True

    def signal_handler(signum, frame):
        nonlocal running
        logger.info("Received signal %s, shutting down consumer...", signum)
        running = False

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    metrics_port = getattr(settings, "CONSUMER_METRICS_PORT", 0)
    if metrics_port:
        from prometheus_client import start_http_server

        start_http_server(metrics_port)
        logger.info("Consumer metrics exposed on :%s/metrics", metrics_port)

    consumer = Consumer({
        "bootstrap.servers": settings.KAFKA_BOOTSTRAP_SERVERS,
        "group.id": "experimentos-event-consumer",
        "auto.offset.reset": "earliest",
        "enable.auto.commit": False,
    })

    topics = [TOPIC_EXPOSURES, TOPIC_CONVERSIONS]
    consumer.subscribe(topics)
    logger.info("Consumer subscribed to topics: %s", topics)

    backoff = 0.0
    try:
        while running:
            msg = consumer.poll(timeout=1.0)
            if msg is None:
                continue

            if msg.error():
                if msg.error().code() == KafkaError._PARTITION_EOF:
                    continue
                logger.error("Kafka consumer error: %s", msg.error())
                continue

            if handle_message(consumer, msg):
                backoff = 0.0
            else:
                backoff = min(MAX_BACKOFF_SECONDS, max(0.5, backoff * 2))
                time.sleep(backoff)

    finally:
        try:
            consumer.commit(asynchronous=False)
        except Exception:
            pass  # nothing to commit
        consumer.close()
        logger.info("Consumer shut down.")
