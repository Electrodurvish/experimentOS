# ExperimentOS Architecture

ExperimentOS is a modular Django monolith plus a small number of separately scaled
processes. Each backing store exists to solve one specific problem (see
[ADRs](adr/)).

## System overview

```mermaid
flowchart TB
    subgraph Clients
        UI[React dashboard<br/>JWT]
        SDK[Application SDKs<br/>X-API-Key]
    end

    subgraph K8s["Kubernetes (Helm / ArgoCD)"]
        FE[frontend<br/>nginx]
        API[api<br/>Django + DRF + gunicorn<br/>HPA]
        CONS[event-consumer<br/>HPA]
        WORK[celery-worker]
        BEAT[celery-beat<br/>1 replica]
    end

    PG[(PostgreSQL<br/>configuration, RBAC,<br/>audit, decisions)]
    REDIS[(Redis<br/>config cache, locks,<br/>dedup, rate limits)]
    SCYLLA[(ScyllaDB / Cassandra<br/>sticky assignments)]
    KAFKA{{Kafka<br/>exposures, conversions}}
    CH[(ClickHouse<br/>events, telemetry)]
    RMQ{{RabbitMQ<br/>Celery jobs}}
    LLM[[Claude API<br/>explanations only]]

    UI --> FE --> API
    SDK --> API
    API --> PG
    API --> REDIS
    API --> SCYLLA
    API -- produce --> KAFKA
    KAFKA --> CONS --> CH
    CONS --> REDIS
    API -- query --> CH
    BEAT -- schedule --> RMQ --> WORK
    WORK --> PG
    WORK --> CH
    API -. evidence .-> LLM

    subgraph Observability
        OTEL[OTel collector] --> TEMPO[Tempo]
        OTEL --> LOKI[Loki]
        PROM[Prometheus] --> GRAF[Grafana]
        SENTRY[Sentry]
    end
    API -. traces .-> OTEL
    PROM -. scrape /metrics .-> API
    PROM -. scrape :9100 .-> CONS
```

## Django apps

| App | Responsibility |
|---|---|
| `accounts` | Users, JWT auth, project API keys (SHA-256 hashed) |
| `organizations` | Organizations, projects, memberships and RBAC (`permissions.py`) |
| `experiments` | Experiments, immutable versions, variants, targeting rules, lifecycle state machine |
| `engine` | Targeting evaluator, MurmurHash bucketing, rollout gate, sticky bucketing, Redis cache and locks, evaluate/debug APIs |
| `events` | Kafka producer/consumer, Redis dedup, ClickHouse schema and result queries |
| `stats` | Z-tests, Wilson CIs, relative lift (delta method), SRM chi-square, sample size |
| `intelligence` | Health score, segment analysis + Simpson's paradox, interaction detection, timeline |
| `observability` | Prometheus metrics, OTel tracing, Sentry, production telemetry correlation |
| `decisions` | Guardrails, anomaly detection, decision engine, progressive rollout, rollback, Celery jobs |
| `ai` | Evidence bundles and LLM explanations with template fallback |
| `audit` | Audit log with standardized actions, organization scope and client IP |

## Evaluation hot path

```mermaid
sequenceDiagram
    participant App as App (SDK)
    participant API as api /evaluate
    participant R as Redis
    participant PG as PostgreSQL
    participant S as ScyllaDB
    participant K as Kafka

    App->>API: POST /api/v1/evaluate (X-API-Key)
    API->>R: GET exp:config:{project}:{key}
    alt cache miss
        API->>PG: load experiment + current version
        API->>R: SETEX config (5 min)
    end
    Note over API: status RUNNING? version active?<br/>targeting AST matches?<br/>rollout gate: hash(user:key:rollout) < rollout%
    API->>S: sticky assignment?
    alt no sticky
        Note over API: bucket = murmur3(user:key:version) % 10000<br/>bucket < traffic_allocation → variant range
        API->>S: save sticky
    end
    API-->>K: exposure event (async, fire-and-forget)
    API->>App: variant, payload, version
```

Key properties:

- **Deterministic**: the variant bucket is `murmur3("{user}:{key}:{version}") % 10000`.
- **Sticky**: once assigned, ScyllaDB returns the same variant even after a new version
  changes bucket ranges (unless that variant no longer exists).
- **Monotonic rollout**: the rollout gate hashes `"{user}:{key}:rollout"` (no version), so
  users inside 10% stay inside at 25/50/100%, and a rollback 50% → 10% keeps the original 10%.
  The gate applies before the sticky lookup, so rollbacks take effect for already-assigned users.
- **Degrades gracefully**: Redis errors fall back to PostgreSQL; Kafka errors are logged and
  counted (`errors_total{component="kafka_producer"}`), never surfaced to the SDK.
- The **debugger** (`/evaluate/debug/`) runs the same pipeline with `persist=False` and returns
  every step; it never writes assignments.

## Event pipeline

```mermaid
flowchart LR
    SDK -- /events/track --> API
    API -- exposure on assign --> T1[(experiment-exposures)]
    API -- conversion --> T2[(conversion-events)]
    T1 --> C[event-consumer]
    T2 --> C
    C -- "SET dedup:{event_id} NX EX 86400" --> R[(Redis)]
    C -- insert --> CH[(ClickHouse)]
    CH -- "single query: first-exposure variant,<br/>converting users after exposure" --> RES[/results, health, decisions/]
```

Exactly-once is approximated with at-least-once delivery plus idempotent processing
(Redis `SETNX` on `event_id`). Known gaps are documented in
[failure-testing.md](failure-testing.md).

## Decision loop

```mermaid
flowchart TB
    BEAT[celery-beat every 5 min] --> JOB[evaluate_running_experiments]
    JOB --> GATHER[gather_inputs]
    GATHER --> S1[stats: lift, p-value, SRM, sample size]
    GATHER --> S2[health score]
    GATHER --> S3[guardrails vs telemetry / conversion]
    GATHER --> S4[production impact]
    GATHER --> S5[time-series anomalies]
    GATHER --> S6[segments / interactions<br/>when supplied]
    S1 & S2 & S3 & S4 & S5 & S6 --> DECIDE["decide() — pure function<br/>recommendation + confidence<br/>+ numbered evidence + checks"]
    DECIDE --> PERSIST[(Decision row)]
    DECIDE --> GATE{RolloutPolicy allows<br/>unattended action?}
    GATE -- ROLLBACK / PAUSE / DECREASE<br/>auto_rollback + confidence --> ACT[change rollout / pause]
    GATE -- INCREASE<br/>auto_advance + min stage duration --> ACT
    GATE -- COMPLETE / CONTINUE --> NOOP[no automatic action]
    ACT --> AUDIT[audit log + timeline + cache invalidation]
    ACT --> ALERT[send_alert → webhook]
```

Rule priority inside `decide()`: guardrail breach → critical anomaly → SRM → significant
primary-metric regression → critical production regression → low health → positive path
(increase / complete) → continue. `COMPLETE` is never executed automatically.

## AI layer

The AI layer is an explanation interface over structured evidence, not a decision maker:

1. `build_experiment_evidence()` turns decision checks, results, rollout history, applied
   decisions, timeline and assignment counts into numbered statements `E1..En`.
2. The model (`AI_MODEL`, default `claude-opus-5`) receives only that JSON, must cite
   IDs, and returns structured JSON. Citations to unknown IDs are dropped.
3. Without credentials, on refusal, or on API errors, a deterministic template answer is built
   from the same evidence, so explanations never block on the LLM.

## Security model

- **Authentication**: JWT for the dashboard, hashed API keys for SDK traffic (one key per project).
- **Authorization**: `OrganizationRolePermission` is a default DRF permission. Every
  organization-owned resource resolves its organization; non-members get `404`, members
  below the required role get `403`. Roles: `VIEWER` (read) < `ANALYST` (run analyses, ask AI,
  preview decisions) < `EXPERIMENT_MANAGER` (create/change experiments, rollouts, guardrails,
  apply decisions) < `ADMIN` (members, projects, API keys).
- **Rate limiting**: per API key for SDK endpoints, per IP for login/registration, per user for
  the dashboard, with a separate budget for AI endpoints. Counters live in Redis.
- **Audit**: `EXPERIMENT_*`, `ROLLOUT_CHANGED`, `ROLLBACK_TRIGGERED`, `CONFIG_CHANGED`,
  `PERMISSION_CHANGED`, `API_KEY_*`, each with actor, organization, before/after and client IP.
- **Input validation**: targeting rules are validated for known operators, bounded depth/size,
  and regexes that compile, are short, and avoid nested quantifiers.

## Data responsibilities

| Store | Holds | Why this store |
|---|---|---|
| PostgreSQL | Configuration, versions, RBAC, audit, decisions, rollout history | Source of truth; relational integrity and transactions |
| Redis | Config cache, distributed locks, event dedup keys, throttle counters | Sub-millisecond shared state across pods |
| ScyllaDB | Sticky assignments keyed by `(user_id, experiment_id)` | High write volume, single-partition reads |
| ClickHouse | Exposures, conversions, production telemetry | Columnar aggregation over large event volumes |
| Kafka | Exposure/conversion streams | Durable, replayable high-volume streaming |
| RabbitMQ | Celery jobs | Task semantics: acks, retries, routing |
