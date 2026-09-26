# ExperimentOS

An experimentation and release platform focused on **trustworthy results, production safety,
explainability and automated decisions**. It answers five questions for every experiment:

1. Which variant did this user receive? — deterministic, sticky assignment with a step-by-step debugger
2. Is the result statistically trustworthy? — z-tests, confidence intervals, SRM, sample size, health score
3. Why did it happen? — segment analysis, Simpson's paradox and interaction detection, evidence-based AI explanations
4. Did it hurt production? — per-variant telemetry, guardrails, anomaly detection, OpenTelemetry traces
5. Continue, pause or roll back? — a decision engine with evidence, progressive rollout and automatic rollback

See [docs/architecture.md](docs/architecture.md) for diagrams and [docs/adr/](docs/adr/) for design decisions.

## Stack

| Layer | Technology |
|---|---|
| API | Python 3.12, Django 5, Django REST Framework, gunicorn |
| Frontend | React, TypeScript, Vite (`frontend/`) |
| Configuration store | PostgreSQL |
| Cache, locks, dedup, rate limits | Redis |
| Sticky assignments | ScyllaDB / Cassandra |
| Event streaming | Kafka → consumer → ClickHouse |
| Jobs | Celery on RabbitMQ (decision sweeps, health recalculation, alerts) |
| Observability | OpenTelemetry, Prometheus, Grafana, Loki, Tempo, Sentry |
| AI | Claude API over structured evidence, with deterministic fallback |
| Delivery | Docker, Helm, Kubernetes HPA, ArgoCD, Terraform (AWS), GitHub Actions |

## See it running (demo)

```bash
scripts/demo.sh          # builds and starts everything, then loads demo data (~5 min the first time)
scripts/demo.sh down     # stop and delete the demo data
```

Then open http://localhost:8080 and log in as `demo@experimentos.local` / `ExperimentOS-demo-1`.
The demo uses built images and publishes only ports 8080 (dashboard) and 8000 (API), so it works
alongside a local Postgres/Redis and without Docker file sharing for this folder.
In the demo data, `checkout_v3` improves conversion but breaches its error-rate guardrail, so the
decision engine rolls it back from 50% to 10%.

## Quick start (Docker Compose)

```bash
cp .env.example .env              # set SECRET_KEY; ANTHROPIC_API_KEY is optional
docker compose up -d --build
docker compose exec api python manage.py migrate
docker compose exec api python manage.py setup_kafka
docker compose exec api python manage.py setup_clickhouse
docker compose exec api python manage.py setup_cassandra
docker compose exec api python manage.py createsuperuser
```

| Service | URL |
|---|---|
| API + Swagger | http://localhost:8000/api/docs/ |
| Dashboard | see the `frontend` service in `docker-compose.yml` |
| Grafana (admin/admin) | http://localhost:3000 |
| Prometheus | http://localhost:9090 |
| RabbitMQ management | http://localhost:15672 |

## Using it

```python
# pip install ./sdk/python
from experimentos_sdk import ExperimentOSClient

client = ExperimentOSClient("http://localhost:8000", api_key="xos_live_...")
client.evaluate("checkout_v3", user_id="123", attributes={"country": "IN", "platform": "android"}).to_dict()
# {"variant": "treatment", "experiment": "checkout_v3", "version": 4}
client.track("purchase", user_id="123", value=49.0)
client.send_telemetry(experiment_id, "treatment", "latency_ms", 182.0)
```

Main API groups (full reference at `/api/docs/`):

| Area | Endpoints |
|---|---|
| Experiments | `POST/GET /api/v1/experiments/`, `POST .../{id}/versions/`, `.../{id}/start/`, `.../{id}/pause/`, `.../{id}/transition/` |
| Evaluation (API key) | `POST /api/v1/evaluate/`, debugger `POST /api/v1/evaluate/debug/` |
| Events (API key) | `POST /api/v1/events/track/`, `POST /api/v1/observability/telemetry[/batch]/` |
| Analytics | `GET .../{id}/results/`, `.../results/srm/`, `.../health/`, `POST .../segments/`, `GET .../timeline/`, `POST /api/v1/interactions/` |
| Production | `GET .../{id}/production-impact/`, `.../anomalies/` |
| Decisions and rollout | `GET/POST .../{id}/decision/`, `GET .../decisions/`, `GET/POST .../rollout/`, `POST .../rollback/`, `.../rollout-policy/`, `.../guardrails/` |
| AI | `GET .../{id}/explain/`, `POST .../{id}/ask/`, `POST /api/v1/ai/query/` |
| Access | `/api/v1/auth/token/`, `/api/v1/organizations/{id}/members/`, `/api/v1/auth/api-keys/`, `/api/v1/audit-logs/` |

Roles per organization: `VIEWER` < `ANALYST` < `EXPERIMENT_MANAGER` < `ADMIN`
(details in [architecture.md](docs/architecture.md#security-model)).

## Development

```bash
poetry install
poetry run pytest                  # unit + API tests (SQLite, external services mocked)
poetry run ruff check .

# End-to-end test against a real ClickHouse
docker run -d -p 18123:8123 -e CLICKHOUSE_DEFAULT_ACCESS_MANAGEMENT=1 clickhouse/clickhouse-server:24.3
E2E_CLICKHOUSE_HOST=localhost E2E_CLICKHOUSE_PORT=18123 poetry run pytest apps/common/tests/test_e2e.py

cd frontend && npm ci && npm run dev    # dashboard on :5173, proxies /api to :8000
cd sdk/python && python -m pytest       # SDK tests
```

## Deployment

- `deploy/helm/experimentos/` — Helm chart: api, event-consumer, celery-worker, celery-beat, frontend,
  HPA, ingress, migration hook.
- `deploy/argocd/` — ArgoCD project and applications (GitOps).
- `deploy/terraform/` — AWS: VPC, EKS, RDS PostgreSQL, ElastiCache Redis, ECR.
- `.github/workflows/` — lint → tests → frontend → image build → Trivy scan → push → Helm values bump.

## Reliability and performance

- [docs/failure-testing.md](docs/failure-testing.md) — what happens when Kafka consumers, Redis,
  PostgreSQL, ClickHouse or API pods fail, and the chaos scripts in `scripts/chaos/`.
- [docs/load-testing.md](docs/load-testing.md) — k6 and Locust scenarios in `loadtest/`.

Performance targets (goals, not measured claims): assignment evaluation P95 < 50 ms, API P95 < 200 ms,
10K+ events/s ingestion. Measured numbers belong in the load-testing results table once a run has been done
on representative infrastructure.
