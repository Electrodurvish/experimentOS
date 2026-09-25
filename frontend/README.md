# ExperimentOS frontend

React 18 + TypeScript (strict) + Vite single-page app for the ExperimentOS Django REST API.
Dependencies are deliberately small: `react-router-dom` for routing and `recharts` for the results chart.
Styling is hand-written CSS with custom properties and automatic light/dark themes (`prefers-color-scheme`).

## Running

```bash
cd frontend
npm install

npm run dev          # http://localhost:5173, proxies /api, /healthz, /readyz, /metrics → http://localhost:8000
npm run build        # tsc -b (type-check) + vite build → dist/
npm run lint         # ESLint flat config (typescript-eslint, react-hooks, react-refresh), zero warnings allowed
npm test -- --run    # Vitest + Testing Library (jsdom), single run
npm run preview      # serve the production build locally
```

Point the dev proxy at another API with `VITE_API_PROXY=http://host:port` in `frontend/.env.local`.
Optional build-time links: `VITE_GRAFANA_URL` (default `http://localhost:3000`) and `VITE_PROMETHEUS_URL` (default `http://localhost:9090`).

Sign in with an existing backend user (JWT from `POST /api/v1/auth/token/`). Create one with
`python manage.py createsuperuser` or `POST /api/v1/auth/register/`.

## Docker

```bash
docker build -t experimentos-frontend frontend
docker run -p 8080:80 -e API_UPSTREAM=http://api:8000 experimentos-frontend
```

The image is a multi-stage build: Node builds `dist/`, and `nginx:alpine` serves it.
`nginx.conf` is installed as `/etc/nginx/templates/default.conf.template`. The nginx entrypoint renders it with
`envsubst`, which gives:

- SPA history fallback (`try_files … /index.html`), with long-lived caching for `/assets/*` and `no-cache` for the shell
- a reverse proxy for `/api/`, `/metrics`, `/healthz` and `/readyz` to `$API_UPSTREAM` (default `http://api:8000`)

nginx resolves the upstream host when it starts, so the API service name must be resolvable by then
(for example, `depends_on: api` in Compose).

## Page map

| Route | Page | Backend endpoints |
|---|---|---|
| `/login` | Sign in | `POST auth/token/`, `GET auth/me/` |
| `/` | Dashboard: counts by status, live experiments with rollout % and health badge | `GET experiments/?status=`, `GET experiments/{id}/health/` |
| `/experiments` | List with search and status, type and project filters, paginated | `GET experiments/`, `GET projects/` |
| `/experiments/new` | Create experiment (project, key, name, type, hypothesis) | `POST experiments/` |
| `/experiments/:id` | Details: overview card (key, status, rollout %, health, control vs treatment, lift) and lifecycle buttons from `allowed_transitions` | `GET experiments/{id}/`, `…/results/`, `…/health/`, `POST …/transition/`, `…/start/`, `…/pause/` |
| `?tab=overview` | Results table, conversion chart with 95% CI, SRM warning, AI explanation, configuration and version history | `…/results/`, `…/explain/` (new), `…/versions/` |
| `?tab=segments` | Segment Explorer: enter rows as a table or JSON to see lift, significance, contribution % and Simpson's paradox flags | `POST …/segments/` |
| `?tab=health` | Health score, per-dimension meters, SRM check | `…/health/`, `…/results/srm/` |
| `?tab=production` | Telemetry impact vs control, harmful anomalies | `…/production-impact/`, `…/anomalies/` |
| `?tab=decision` | Recommendation, confidence, numbered evidence, ✓/✗ checks, record or apply, history | `GET/POST …/decision/`, `…/decisions/` |
| `?tab=rollout` | Rollout control (see below) | |
| `?tab=timeline` | Vertical chronological timeline grouped by day | `…/timeline/` |
| `?tab=audit` | Audit entries for the experiment | `audit-logs/?experiment=` |
| `?tab=ask` | Ask AI about the experiment, with cited evidence highlighted | `POST …/ask/` (new) |
| `/experiments/:id/versions/new` | Version editor: variants, shares, bucket ranges, payloads, targeting JSON, and live validation that mirrors `apps/experiments/validators.py` | `POST …/versions/` |
| `/rollout` | Rollout Control: current %, stage buttons from `policy.stages`, custom %, rollback with reason, history, policy editor, guardrail CRUD | `…/rollout/`, `…/rollback/`, `…/rollout-policy/`, `…/guardrails/` |
| `/alerts` | PAUSE, ROLLBACK and DECREASE_ROLLOUT decisions, plus `rollback_triggered`, `guardrail_breached` and `anomaly_detected` events, across running and paused experiments | `…/decisions/`, `…/timeline/` |
| `/debugger` | Assignment Debugger: step-by-step trace with pass/fail and the final result | `POST evaluate/debug/` |
| `/interactions` | Interaction detection for pairs of concurrent experiments | `POST interactions/` |
| `/audit` | Audit logs filtered by experiment and action | `GET audit-logs/` |
| `/ai` | Portfolio-wide AI query | `POST ai/query/` (new) |
| `/system` | `/healthz` and `/readyz` status, links to Grafana, Prometheus, `/metrics` and the API docs | |

## Conventions

- **Units.** Rollout, traffic allocation, variant `traffic_percentage` and policy stages are basis points
  (`5000` = 50%). Conversion rates and lifts are fractions (`0.124` = 12.4%). All conversions live in `src/lib/format.ts`.
- **API client.** `src/api/` holds one typed module. `client.ts` stores JWTs in localStorage, attaches
  `Authorization: Bearer`, and on a 401 refreshes the access token once and retries. If the refresh fails, it clears
  the session and the app returns to `/login`. `index.ts` has one typed function per endpoint, and `types.ts` mirrors
  the serializers.
- **New endpoints.** If `explain`, `ask` or `ai/query` returns 404, 405 or 501, the page shows a friendly
  "isn't available yet" notice instead of an error.
- **Roles.** When `GET auth/me/` includes `memberships`, users whose roles are only `ANALYST` or `VIEWER` get a
  read-only UI: create, transition, rollout, policy, guardrail and decision-apply controls are hidden.
  The backend still enforces permissions.

## Layout

```
src/
  api/          client.ts (fetch + JWT refresh), index.ts (endpoints), types.ts
  auth/         AuthProvider + useAuth
  components/   Layout, ExperimentHeader, RolloutPanel, Timeline, Evidence, ConversionChart, ui primitives
  lib/          pure logic: format, buckets (variant validation), segments, alerts, results, roles, rollout, hooks
  pages/        route components; pages/tabs/ for the experiment detail tabs
  styles.css    design tokens + all styles
```
