"""
Kafka → ClickHouse event consumer.

Delivery semantics: at-least-once from Kafka, made idempotent with a Redis
key per event_id that is written only after the event is stored.

- Offsets are committed only after an event is stored (or deliberately skipped),
  so a crash between poll and insert re-delivers the event instead of losing it.
- The dedup key is set after a successful insert. Producers key messages by
  user_id, so redeliveries of an event land on the same partition and are
  processed sequentially by one consumer; check-then-set is therefore race-free.
- ClickHouse unreachable: rewind to the failed offset and retry with exponential
  backoff (up to MAX_BACKOFF_SECONDS) for as long as the outage lasts.
- Event rejected (bad data / schema error): retry up to MAX_ATTEMPTS, then publish
  the raw message to "<topic>.dlq" and commit, so one bad event cannot block its
  partition.
- The main loop touches CONSUMER_HEARTBEAT_FILE every iteration for the
  liveness probe (manage.py consumer_healthcheck).
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
MAX_ATTEMPTS = 5


def _dedup_key(event_id):
    return f"dedup:{event_id}"


def is_duplicate(event_id):
    """True if this event_id was already stored. Redis errors fail open (process the event)."""
    try:
        return bool(get_redis_client().exists(_dedup_key(event_id)))
    except Exception:
        logger.warning("Redis dedup check failed, processing event anyway", exc_info=True)
        return False


def mark_processed(event_id):
    """Remember that event_id has been stored, for EVENT_DEDUP_TTL seconds."""
    try:
        ttl = getattr(settings, "EVENT_DEDUP_TTL", 86400)
        get_redis_client().set(_dedup_key(event_id), "1", ex=ttl)
    except Exception:
        logger.warning("Failed to record dedup key for %s", event_id, exc_info=True)


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
        record_event_consumed(topic, "failed")
        raise

    mark_processed(event_id)
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


_attempts = {}


def _send_to_dlq(msg, error):
    """Publish a rejected message to <topic>.dlq. Returns True once the broker confirmed delivery."""
    from apps.events.producer import _get_producer

    producer = _get_producer()
    if producer is None:
        return False
    delivered = []
    producer.produce(
        topic=f"{msg.topic()}.dlq",
        key=msg.key(),
        value=msg.value(),
        headers={"error": str(error)[:500], "source_offset": str(msg.offset())},
        callback=lambda err, _m: delivered.append(err is None),
    )
    producer.flush(10)
    return delivered == [True]


def handle_message(consumer, msg):
    """
    Process one Kafka message and commit its offset, or rewind for retry.
    Returns True when the offset was committed, False when it will be retried.
    """
    from confluent_kafka import TopicPartition

    from apps.events.clickhouse import EventStoreUnavailableError

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

    position = (topic, msg.partition(), msg.offset())
    try:
        processor(event)
    except EventStoreUnavailableError:
        logger.warning("ClickHouse unavailable at %s:%s; will retry", topic, msg.offset())
        record_error("event_consumer", "store_unavailable")
        consumer.seek(TopicPartition(*position))
        return False
    except Exception as exc:
        attempts = _attempts.get(position, 0) + 1
        _attempts[position] = attempts
        record_error("event_consumer", "event_rejected")
        if attempts < MAX_ATTEMPTS:
            logger.warning("Event at %s:%s rejected (attempt %s/%s): %s", topic, msg.offset(), attempts,
                           MAX_ATTEMPTS, exc)
            consumer.seek(TopicPartition(*position))
            return False
        if not _send_to_dlq(msg, exc):
            logger.error("Could not publish rejected event at %s:%s to DLQ; will retry", topic, msg.offset())
            consumer.seek(TopicPartition(*position))
            return False
        logger.error("Event at %s:%s sent to %s.dlq after %s attempts: %s", topic, msg.offset(), topic,
                     attempts, exc)
        record_event_consumed(topic, "dead_lettered")

    _attempts.pop(position, None)
    consumer.commit(message=msg, asynchronous=True)
    return True


def touch_heartbeat():
    path = getattr(settings, "CONSUMER_HEARTBEAT_FILE", "")
    if not path:
        return
    try:
        with open(path, "w") as f:
            f.write(str(time.time()))
    except OSError:
        logger.warning("Could not write consumer heartbeat to %s", path, exc_info=True)


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
        # Pick up topics created after startup (e.g. the first conversion) within seconds,
        # not the 5-minute librdkafka default.
        "topic.metadata.refresh.interval.ms": 10000,
    })

    topics = [TOPIC_EXPOSURES, TOPIC_CONVERSIONS]
    consumer.subscribe(topics)
    logger.info("Consumer subscribed to topics: %s", topics)

    backoff = 0.0
    try:
        while running:
            touch_heartbeat()
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
