# Load testing

This is how ExperimentOS performance is measured. The plan's numbers
(section 47) are **engineering targets, not claims**; the results table at the
end is empty until someone runs these tests on recorded hardware.

| Target (plan §47) | Where it is encoded |
|---|---|
| Assignment evaluation P95 < 50 ms | `loadtest/k6/evaluate.js` threshold on `http_req_duration{name:evaluate}`; Prometheus alert `EvaluationLatencyHigh` (`infra/prometheus/alerts.yml`) |
| API P95 < 200 ms | `loadtest/k6/track.js` threshold; alert `ApiLatencyHigh` |
| Event ingestion 10K+ events/s | Measured from `events_consumed_total` on the consumer (see below); no k6 threshold because the HTTP API only enqueues |
| Dashboard queries sub-second to few seconds | Not load-tested yet (ClickHouse queries via `/api/v1/experiments/{id}/results/`) |

## Tools

- `loadtest/seed.py`: creates a user, org, project, N running 50/50 A/B
  experiments and an SDK API key through the REST API; writes
  `loadtest/seed.json` (gitignored, it contains a live key).
- `loadtest/k6/evaluate.js`: `POST /api/v1/evaluate/`, open-model
  (constant arrival rate) at 100/500/1000/5000 RPS or a ramp through all of them.
- `loadtest/k6/track.js`: `POST /api/v1/events/track/`, with an optional
  duplicate-event ratio for de-duplication checks.
- `loadtest/locustfile.py`: Locust alternative (closed model; fine for
  exploratory runs, prefer k6 for the RPS ladder).
- `loadtest/docker-compose.loadtest.yml`: compose overlay that runs the api
  under gunicorn instead of `runserver`, with DEBUG off and the SDK throttle raised.

Install: `brew install k6` (or see k6.io), `pip install locust`.

## Running against docker-compose

```bash
# 1. Stack with gunicorn instead of the dev server
docker compose -f docker-compose.yml -f loadtest/docker-compose.loadtest.yml up -d --build
docker compose exec api python manage.py migrate
docker compose exec api python manage.py setup_clickhouse
docker compose exec api python manage.py setup_cassandra

# 2. Seed
python3 loadtest/seed.py --base-url http://localhost:8000 --out loadtest/seed.json

# 3. Smoke (5 req/s for 15s): checks the wiring, not performance
k6 run loadtest/k6/evaluate.js

# 4. The ladder: one fixed rate per run, 2 minutes steady state each
mkdir -p loadtest/results
for rps in 100 500 1000 5000; do
  k6 run -e PROFILE=$rps -e SUMMARY_FILE=loadtest/results/evaluate-$rps.json loadtest/k6/evaluate.js
done
k6 run -e PROFILE=1000 -e SUMMARY_FILE=loadtest/results/track-1000.json loadtest/k6/track.js

# Or a single ramp 100 -> 500 -> 1000 -> 5000
k6 run -e PROFILE=ramp loadtest/k6/evaluate.js
```

Useful knobs: `DURATION=5m`, `USER_POOL=1000000` (distinct user ids; affects
sticky-assignment lookups and PostgreSQL assignment upserts),
`KEYS_PER_REQUEST=1`, `LT_GUNICORN_THREADS=16`, `LT_GUNICORN_WORKERS=4`
(see the metrics caveat below).

### Reading the result honestly

- **`dropped_iterations` > 0 means the target rate was not achieved.** k6 ran
  out of VUs because responses got slow. Report the achieved `http_reqs` rate,
  not the requested one.
- A 429 is a failure (the SDK throttle), not throughput. The overlay raises
  `SDK_THROTTLE_RATE`; in Kubernetes set `config.SDK_THROTTLE_RATE`.
- k6 on the same laptop as the stack competes for CPU with the server. For
  the 1000/5000 RPS rows, run k6 from a separate machine or at least record that
  it was co-located.
- Client-side latency (k6) includes network, auth and serialization. Also
  record the server-side view from Prometheus (below) - both belong in the table.

## Server-side measurements (Prometheus on :9090)

```promql
# API P95 by endpoint
histogram_quantile(0.95, sum by (le, endpoint) (rate(http_request_duration_seconds_bucket[1m])))

# Evaluation P95 (the assignment function itself, excluding HTTP/auth)
histogram_quantile(0.95, sum by (le) (rate(experiment_evaluation_duration_seconds_bucket[1m])))

# Achieved request rate / error rate
sum(rate(http_requests_total[1m]))
sum(rate(http_requests_total{status=~"5.."}[1m])) / sum(rate(http_requests_total[1m]))

# End-to-end ingestion throughput (Kafka -> consumer -> ClickHouse)
sum by (result) (rate(events_consumed_total[1m]))

# Cache effectiveness during the run
rate(experiment_cache_hits_total[1m]) / (rate(experiment_cache_hits_total[1m]) + rate(experiment_cache_misses_total[1m]))
```

**Metrics caveat:** the api uses the default in-process `prometheus_client`
registry (`apps/observability/views.py:150-162`), not multiprocess mode. With
more than one gunicorn worker per container, each scrape returns one worker's
counters only. That is why the Dockerfile and Helm chart default to 1 worker x
8 threads per pod. If you raise `LT_GUNICORN_WORKERS`, use k6's numbers, not
Prometheus', until `PROMETHEUS_MULTIPROC_DIR` support is added.

### Ingestion throughput (10K events/s target)

The HTTP API returns 202 once the event is handed to the Kafka producer's local
buffer, so k6's track numbers only measure the API. To measure the pipeline:

1. Run `track.js` at a fixed rate for a few minutes.
2. Compare `sum(rate(events_produced_total[1m]))` (api) with
   `sum(rate(events_consumed_total{result="processed"}[1m]))` (consumer).
3. Consumer lag: `docker compose exec kafka kafka-consumer-groups --bootstrap-server localhost:29092 --describe --group experimentos-event-consumer`.
   Lag that grows steadily = the consumer is the bottleneck at that rate.
4. Row count check: `docker compose exec clickhouse clickhouse-client -q "SELECT count() FROM experimentos.conversion_events"`.

The consumer inserts **one row per ClickHouse INSERT**
(`apps/events/clickhouse.py:99-160`) and commits each offset individually,
from a single poll loop (`apps/events/consumer.py:169-186`). ClickHouse recommends batched inserts;
expect this design to be the limiting factor well before 10K events/s. Scaling
out needs more topic partitions (the compose broker auto-creates topics with 1
partition) and consumer replicas; batching needs a backend change.

## Horizontal scaling test (Kubernetes, plan §36)

With the Helm chart deployed (`api.autoscaling.enabled=true`, metrics-server installed):

```bash
kubectl -n experimentos get hpa -w &
k6 run -e BASE_URL=https://<host> -e SEED_FILE=/abs/path/seed.json -e PROFILE=ramp loadtest/k6/evaluate.js
```

Record replicas vs. sustained RPS at P95 < 50 ms. To measure per-pod capacity,
disable the HPA, pin `api.replicaCount` to 1, 2, 5 and find the highest
fixed-rate profile each sustains without `dropped_iterations` or threshold failures.

## Bottlenecks visible in the code (to confirm or rule out with measurements)

| Where | What happens per evaluate request |
|---|---|
| `apps/accounts/authentication.py:18-31` | API key lookup (SELECT) **and** an `UPDATE ... last_used_at` on every request |
| `apps/engine/assigner.py:292-310` | `Assignment.objects.update_or_create` (SELECT + INSERT/UPDATE) per assigned experiment, on cache hits too (the cached-path bug where this write was silently skipped was fixed in commit ac76b95 - benchmarks from before that commit under-count DB work) |
| `apps/engine/sticky.py:46-73` | Cassandra read + write per computed assignment |
| `apps/common/throttling.py` + DRF `SimpleRateThrottle` | The throttle stores a list of request timestamps per key in the Redis-backed Django cache and rewrites it on every request; at thousands of req/s per key the list (and each GET/SET) grows with the rate |
| `apps/events/producer.py:77-83` | `produce()` + `poll(0)` - cheap, asynchronous |

## Results

Fill in one row per run. Leave nothing estimated; "not run" is a valid entry.

**Environment for these runs:** (machine / instance types, CPU, RAM, where k6
ran, gunicorn workers x threads, api replicas, commit SHA)

### Evaluate (`POST /api/v1/evaluate/`, 3 experiments per request)

| Target RPS | Achieved RPS | Dropped iterations | Client P50 | Client P95 | Client P99 | Server eval P95 (Prometheus) | Error % | api pods / workers | Date / commit |
|---|---|---|---|---|---|---|---|---|---|
| 100 | | | | | | | | | |
| 500 | | | | | | | | | |
| 1,000 | | | | | | | | | |
| 5,000 | | | | | | | | | |

### Track (`POST /api/v1/events/track/`)

| Target RPS | Achieved RPS | Client P95 | Error % | Consumer processed/s | Max consumer lag | Date / commit |
|---|---|---|---|---|---|---|
| 100 | | | | | | |
| 500 | | | | | | |
| 1,000 | | | | | | |
| 5,000 | | | | | | |

### Horizontal scaling

| api pods | Max sustained RPS (P95 < 50 ms, 0 dropped) | CPU per pod at that rate | Date / commit |
|---|---|---|---|
| 1 | | | |
| 2 | | | |
| 5 | | | |
