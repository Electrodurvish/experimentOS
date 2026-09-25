# Failure testing

Plan section 46: intentionally kill the Kafka consumer, Redis, PostgreSQL,
ClickHouse and the API, and document what happens. This page records, per
scenario, what the **code** says should happen (with file:line references),
how to reproduce it, what was **observed**, and the gaps visible in the code.

"To be measured" means the scenario has a script but has not been run against
the full stack yet. Do not replace it with an expectation; replace it with the
script output, the date and the commit.

> Scenario expectations were written against commit `a48e99a` and updated after
> the gap fixes listed under [Known gaps](#known-gaps-from-reading-the-code)
> (all ten are now addressed in code). Re-check line numbers when you re-run.

## How to run

```bash
docker compose up -d
docker compose exec api python manage.py migrate
docker compose exec api python manage.py setup_clickhouse
docker compose exec api python manage.py setup_cassandra

scripts/chaos/run-all.sh                  # every scenario, log in scripts/chaos/results/
scripts/chaos/kill-redis.sh               # or one at a time
OUTAGE=60 scripts/chaos/kill-postgres.sh  # knobs: OUTAGE, N, COPIES, LOAD_WORKERS
```

The scripts seed their own experiment + API key through the REST API
(`loadtest/seed.py`) if `loadtest/seed.json` does not exist, run a background
evaluate load (4 curl loops, ~20 req/s each) where relevant, stop/kill a compose
service, and print PASS/FAIL lines against the expected behaviour below. A FAIL
is a finding, not a script bug to be silenced.

Raise the SDK throttle for the stack before running
(`SDK_THROTTLE_RATE=100000/min` in `.env`), otherwise the background load can
hit HTTP 429 from `apps/common/throttling.py` and muddy the results. (Throttles
fail open when Redis is unreachable, so they do not cause 500s in scenario 3.)

## Scenario summary

| # | Failure | Expected behaviour (from code) | How to run | Observed | Alert that should fire |
|---|---|---|---|---|---|
| 1 | Kafka consumer killed (SIGKILL) while events arrive | API keeps returning 202. Events wait in Kafka. On restart the group resumes from the last committed offset; offsets are committed only after a successful insert, so nothing is lost and re-deliveries are de-duplicated. | `scripts/chaos/kill-consumer.sh` | To be measured | `EventConsumerDown` (target gone) or `EventConsumerStalled` |
| 2 | Kafka broker down | API keeps returning 202; librdkafka buffers and retries. Outages under `message.timeout.ms` (30 s) are delivered on recovery; longer ones drop the queued events and each drop is counted in `errors_total{component="kafka_producer",error_type="delivery_failed"}`. | `scripts/chaos/kill-kafka.sh` | To be measured | `KafkaProduceFailures` |
| 3 | Redis down | Config cache errors are swallowed and evaluation falls back to PostgreSQL; throttles fail open; locks fail closed (409 on transitions); consumer dedup fails open. Redis sockets time out after 0.25 s (0.5 s for the Django cache), so partitions do not hang threads. | `scripts/chaos/kill-redis.sh` | Before the G2 fix: `/evaluate` returned **HTTP 500** (below). After: to be measured | `errors_total{component="throttle"}` / `{component="redis"}` rising |
| 4 | PostgreSQL down | `/healthz` stays 200 (no restart loop), `/readyz` 503 (pod leaves endpoints). `/evaluate` fails: API-key auth reads and writes PostgreSQL before the Redis cache is used. Recovers without restart. | `scripts/chaos/kill-postgres.sh` | To be measured | `HighErrorRate` |
| 5 | ClickHouse down | API unaffected. The insert raises `EventStoreUnavailableError`; the consumer rewinds to the failed offset and retries with backoff (max 30 s) for as long as the outage lasts (no dead-lettering for outages). No loss; the partition catches up on recovery. Results endpoints return empty data. | `scripts/chaos/kill-clickhouse.sh` | To be measured | `EventStoreUnavailable`, then `EventConsumerStalled` |
| 6 | API process killed | compose: no restart policy, stays down until started. Kubernetes: Deployment replaces the pod; with 2+ replicas and the PDB, the Service keeps serving. A SIGKILL loses producer-buffered events in that process; a graceful stop flushes them (`atexit` + gunicorn `worker_exit`). | `scripts/chaos/kill-api.sh` (compose) / `MODE=k8s scripts/chaos/kill-api.sh` | To be measured | `HighErrorRate` if single replica; none expected with 2+ |
| 7 | Same event delivered many times | API accepts every copy. Consumer SETNX on `dedup:<event_id>` (24h TTL) lets exactly one through: one ClickHouse row per event_id. With Redis down, dedup fails open. | `scripts/chaos/duplicates.sh` | To be measured | none |
| 8 | Cassandra/Scylla down (sticky store) | Sticky read/write errors are swallowed; assignment is computed from the hash (same variant unless allocation changed). A failed connect opens a 30 s circuit, so only one request per 30 s pays the (2 s) connect timeout. | not scripted: `docker compose stop cassandra` + `k6 run loadtest/k6/evaluate.js` | To be measured | none expected |
| 9 | RabbitMQ down | Periodic decision/health jobs are not delivered; the API is unaffected (Celery is not on the request path). Tasks use `acks_late`, so a worker crash mid-task re-delivers. | not scripted: `docker compose stop rabbitmq` | To be measured | `CeleryBeatStalled`, `DecisionSweepFailing` |

## Scenario details

### 1. Kafka consumer killed

- Produce path: `TrackEventView.post` -> `produce_conversion` (`apps/events/views.py`, `apps/events/producer.py:90-117`). No consumer involvement, so 202 is expected throughout.
- Consumer config: `enable.auto.commit=False`, `auto.offset.reset=earliest` (`apps/events/consumer.py:158-163`). Offset committed after each stored event (`consumer.py:130`), asynchronously.
- Re-delivery after restart hits `is_duplicate` (`consumer.py:35-48`); already-stored events are skipped.
- The script sends N events with the consumer killed, restarts it and waits for exactly N rows with the run's event_id prefix in `conversion_events`, and reports catch-up time and any surplus rows.
- In Kubernetes the Deployment restarts a crashed consumer. The liveness probe runs `manage.py consumer_healthcheck --max-age 90`, which fails when the poll loop stops writing its heartbeat file, so a **hung** loop is restarted too.

### 2. Kafka broker down

- `producer.produce()` only enqueues locally; `acks=all`, `retries=3`, `message.timeout.ms=30000` (`apps/events/producer.py`). Longer outages drop queued events; `_delivery_callback` counts each drop (`delivery_failed`).
- `events_produced_total` is incremented from the delivery callback on broker acknowledgement, so it reflects delivered events.

### 3. Redis down

Designed degradation, per component:

| Component | Behaviour | Code |
|---|---|---|
| Experiment config cache | read/write errors caught, logged, counted (`errors_total{component="redis"}`), falls back to PostgreSQL | `apps/engine/cache.py:40-65` |
| Distributed locks | acquisition error -> `LockAcquisitionError` -> HTTP 409 for transitions and version creation (fail closed; correct for state changes) | `apps/engine/locks.py:48-63`, `apps/experiments/views.py` (`_transition`, `create_version`) |
| Consumer dedup | fails open: events processed without dedup, so re-deliveries during the outage can create duplicate rows | `apps/events/consumer.py` (`is_duplicate`) |
| DRF throttles | fail open via `FailOpenMixin`: cache errors allow the request and increment `errors_total{component="throttle"}` | `apps/common/throttling.py` |

**Observed (partial, not the compose stack):** on 2026-09-26 with the working
tree at commit `5cc1d70` (rate limiting just added), `runserver` + SQLite +
a Redis container on :6390: with Redis running, `/evaluate` returned 200; after
`docker stop` of Redis, `POST /api/v1/evaluate/` returned **HTTP 500**
(`redis.exceptions.ConnectionError` raised from
`rest_framework/throttling.py` -> `django/core/cache/backends/redis.py`) in
~27 ms. The cache fallback in `apps/engine/cache.py` was never reached. This was
gap G2 and is fixed (throttles fail open); the full `kill-redis.sh` run
(under gunicorn, with load) is still to be measured.

### 4. PostgreSQL down

- `/healthz` has no dependency checks (`apps/common/health.py:7-9`); `/readyz` runs `SELECT 1` and returns 503 on failure (`health.py:12-19`). In Kubernetes this removes pods from the Service without restarting them, which is the intended split.
- Every SDK request authenticates by API key with a SELECT (and an UPDATE of `last_used_at` at most once a minute, `apps/accounts/authentication.py`), so `/evaluate` cannot degrade to the Redis config cache when the database is down.
- Production settings enable `CONN_HEALTH_CHECKS` and `CONN_MAX_AGE=60` (`config/settings/production.py`), so stale connections are replaced after recovery without a restart.
- The script measures `/readyz` recovery time and time to first successful evaluate after `db` is healthy.

### 5. ClickHouse down

- `insert_conversion` / `insert_exposure` raise `EventStoreUnavailableError` for connection problems and `EventRejectedError` for rejected data (`apps/events/clickhouse.py`).
- The dedup key is written only after a successful insert (`consumer.py`, `mark_processed`). `handle_message` seeks back to the failed offset; the loop backs off exponentially up to `MAX_BACKOFF_SECONDS=30`.
- Unavailable: retried indefinitely. Rejected: retried `MAX_ATTEMPTS=5` times, then published to `<topic>.dlq` (with the error in a header) and committed, so one bad event cannot block its partition.
- Consequence: no loss and no duplicates during an outage; the partition catches up when ClickHouse returns.
- The script sends N events during the outage, restarts ClickHouse, and requires all N to appear within 120 s and no surplus rows.

### 6. API process killed

- compose: `api` has no `restart:` policy in `docker-compose.yml`, so the script starts it again and measures errors and time to the first 200.
- Kubernetes: `deploy/helm/experimentos` runs the api with `maxUnavailable: 0`, readiness on `/readyz`, a startup probe, a PDB (`minAvailable`), a 5 s `preStop` sleep and `terminationGracePeriodSeconds: 40`. `MODE=k8s` force-deletes one pod under load and reports client-visible errors.
- `flush_producer()` runs on graceful shutdown (registered with `atexit` when the producer is created, and from the gunicorn `worker_exit` hook in `gunicorn.conf.py`); undelivered messages at exit are counted.

### 7. Duplicate events

- The API does not dedup (`apps/events/views.py`); the consumer does, by `event_id` only, for `EVENT_DEDUP_TTL=86400` s (`config/settings/base.py`).
- The script sends 10 event_ids x 20 copies and expects exactly 10 rows; then repeats one event_id 20 times with Redis stopped and reports how many rows were stored (expected: several, dedup fails open - or 0 if the API itself fails without Redis, see G2).

### 8. Cassandra down

- `get_sticky_assignment` / `save_sticky_assignment` catch all exceptions (`apps/engine/sticky.py:71-73`, `:95-96`), so evaluation continues with the computed (deterministic) assignment.
- `_get_session()` opens a 30 s circuit after a failed connect (`CIRCUIT_BREAK_SECONDS`) and uses a 2 s connect timeout, so evaluations skip Cassandra quickly instead of each paying the connect timeout.

## Known gaps (from reading the code)

All ten gaps below were fixed after this review; the last column says how.

| ID | Gap (as found) | Where | Impact | Fix |
|---|---|---|---|---|
| G1 | `EventConsumerStalled` cannot fire when the consumer is dead or retrying. Dead: its metrics target disappears, so `sum(rate(events_consumed_total[5m])) == 0` has no series and the `and` yields nothing. Retrying (ClickHouse down): `result="failed"` increments `events_consumed_total`, so the rate is non-zero. | `infra/prometheus/alerts.yml` (EventConsumerStalled); `apps/events/consumer.py:75` | Silent pipeline stall | Added `EventConsumerDown` (`up == 0` / absent), stall rule counts only `result="processed"`, plus `EventStoreUnavailable` and `EventsDeadLettered` alerts. A kafka-exporter lag alert is still a good addition. |
| G2 | Throttle state in Redis without fail-open handling turns a Redis outage into 500s for every throttled endpoint, including `/evaluate` and `/events/track` | `apps/common/throttling.py`; `CACHES` in `config/settings/base.py` | Redis becomes a hard dependency of the hot path, defeating the cache fallback in `apps/engine/cache.py` | `FailOpenMixin` on every throttle class; errors counted as `errors_total{component="throttle"}`. |
| G3 | Consumer liveness only checks the metrics HTTP thread | `deploy/helm/experimentos/values.yaml` `eventConsumer.livenessProbe`; `consumer.py:151-156` | A hung poll loop is never restarted | Heartbeat file written every loop iteration; exec liveness probe `manage.py consumer_healthcheck`. |
| G4 | No dead-letter path: an event that ClickHouse rejects permanently (e.g. a type error) is retried forever and blocks its partition | `apps/events/consumer.py:121-128` | Pipeline stall from one bad event | Rejected events retried 5 times then published to `<topic>.dlq` and committed; outages are never dead-lettered. |
| G5 | Kafka delivery failures are only logged; `errors_total{component="kafka_producer"}` counts synchronous `produce()` exceptions only, and `events_produced_total` counts enqueues | `apps/events/producer.py:43-46`, `:84`, `:114` | Broker outages and dropped messages are invisible in metrics; `KafkaProduceFailures` stays silent | Delivery callback counts success (`events_produced_total`) and failure (`delivery_failed`); `message.timeout.ms=30000`. |
| G6 | Producer queue is never flushed on shutdown | `apps/events/producer.py:120-123` (no callers) | Events accepted with 202 are lost on every pod restart/deploy | `flush_producer` registered with `atexit` and called from gunicorn `worker_exit`. |
| G7 | Cassandra outage makes every evaluation retry the cluster connection twice | `apps/engine/sticky.py:28-43` | Evaluation latency spikes by the connect timeout while Cassandra is down | 30 s circuit breaker and 2 s connect timeout in `apps/engine/sticky.py`. |
| G8 | Dedup key is set before the insert; a crash between SETNX and a completed insert loses that event on re-delivery | `apps/events/consumer.py:66-76` | At most one in-flight event per partition per crash | Dedup key written after a successful insert (`mark_processed`); per-user partitioning keeps check-then-set race-free. |
| G9 | No alerting for RabbitMQ/Celery (beat not running, queue growing) | `infra/prometheus/alerts.yml` | Automated decisions/rollbacks silently stop | Beat heartbeat task every minute and decision-sweep timestamp exposed as gauges; `CeleryBeatStalled` and `DecisionSweepFailing` alerts. |
| G10 | Redis client has no socket timeouts | `apps/engine/cache.py:14-23` | A network partition (as opposed to a stopped container, which fails fast) can hang request threads | Socket timeouts on the redis-py pool (0.25 s) and the Django Redis cache (0.5 s). |

## Results log

Append one row per run.

| Date | Commit | Environment | Scenario | Result (PASS/FAIL lines, key numbers) | Notes |
|---|---|---|---|---|---|
| 2026-09-26 | `5cc1d70` (working tree) | runserver + SQLite + Redis container, laptop | 3 (Redis down), manual | `/evaluate` 200 before, **500** during outage (throttle cache `ConnectionError`) | Not the compose stack, not under load; confirms G2 |
| | | | | | |
