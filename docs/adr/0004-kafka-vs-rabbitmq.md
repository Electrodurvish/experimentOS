# ADR 0004: Kafka for event streams, RabbitMQ for jobs

**Status:** Accepted

| | Kafka | RabbitMQ (Celery broker) |
|---|---|---|
| Carries | Exposure and conversion events | Jobs: decision sweeps, health recalculation, alerts |
| Volume | High, bursty, proportional to user traffic | Low, scheduled |
| Semantics needed | Durable ordered log, replay, consumer groups, partition-level scaling | Per-task ack, retry with backoff, routing, visibility of queued work |
| Consumer | `event-consumer` (idempotent via Redis `SETNX`) | `celery-worker` (`acks_late`, prefetch 1) |

## Decision
Use both, each for what it is good at. Events are facts that analytics may need to replay into
ClickHouse; jobs are commands that should run once and be retried on failure.

## Consequences
Two brokers to operate. The alternative (Celery on Kafka, or events on RabbitMQ) would give up
replayability for events or task semantics for jobs.
