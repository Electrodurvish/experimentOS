import json
import logging
import signal

from django.conf import settings

from apps.engine.cache import get_redis_client
from apps.events.clickhouse import insert_conversion, insert_exposure
from apps.events.producer import TOPIC_CONVERSIONS, TOPIC_EXPOSURES
from apps.observability.metrics import record_event_consumed

logger = logging.getLogger(__name__)


def is_duplicate(event_id):
    """
    Check if an event has already been processed using Redis SETNX.
    Returns True if duplicate (already processed), False if new.
    """
    try:
        client = get_redis_client()
        key = f"dedup:{event_id}"
        ttl = getattr(settings, "EVENT_DEDUP_TTL", 86400)
        # SET NX returns True if key was set (new event), False if exists (duplicate)
        was_set = client.set(key, "1", nx=True, ex=ttl)
        return not was_set
    except Exception:
        logger.warning("Redis dedup check failed, processing event anyway", exc_info=True)
        return False


def process_exposure(event):
    """Process a single exposure event: deduplicate and insert into ClickHouse."""
    event_id = event.get("event_id")
    if not event_id:
        logger.warning("Exposure event missing event_id, skipping")
        record_event_consumed(TOPIC_EXPOSURES, "invalid")
        return

    if is_duplicate(event_id):
        logger.debug("Duplicate exposure event %s, skipping", event_id)
        record_event_consumed(TOPIC_EXPOSURES, "duplicate")
        return

    insert_exposure(event)
    record_event_consumed(TOPIC_EXPOSURES, "processed")
    logger.debug("Processed exposure event %s", event_id)


def process_conversion(event):
    """Process a single conversion event: deduplicate and insert into ClickHouse."""
    event_id = event.get("event_id")
    if not event_id:
        logger.warning("Conversion event missing event_id, skipping")
        record_event_consumed(TOPIC_CONVERSIONS, "invalid")
        return

    if is_duplicate(event_id):
        logger.debug("Duplicate conversion event %s, skipping", event_id)
        record_event_consumed(TOPIC_CONVERSIONS, "duplicate")
        return

    insert_conversion(event)
    record_event_consumed(TOPIC_CONVERSIONS, "processed")
    logger.debug("Processed conversion event %s", event_id)


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
        "enable.auto.commit": True,
        "auto.commit.interval.ms": 5000,
    })

    topics = [TOPIC_EXPOSURES, TOPIC_CONVERSIONS]
    consumer.subscribe(topics)
    logger.info("Consumer subscribed to topics: %s", topics)

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

            try:
                event = json.loads(msg.value().decode("utf-8"))
            except (json.JSONDecodeError, UnicodeDecodeError):
                logger.warning("Failed to decode message from topic %s", msg.topic())
                continue

            topic = msg.topic()
            if topic == TOPIC_EXPOSURES:
                process_exposure(event)
            elif topic == TOPIC_CONVERSIONS:
                process_conversion(event)
            else:
                logger.warning("Received message from unexpected topic: %s", topic)

    finally:
        consumer.close()
        logger.info("Consumer shut down.")
