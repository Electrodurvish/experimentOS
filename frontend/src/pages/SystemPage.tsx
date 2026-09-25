import { system } from '../api';
import { Badge, Card, ErrorBox } from '../components/ui';
import { useAsync } from '../lib/useAsync';

const GRAFANA_URL = import.meta.env.VITE_GRAFANA_URL ?? 'http://localhost:3000';
const PROMETHEUS_URL = import.meta.env.VITE_PROMETHEUS_URL ?? 'http://localhost:9090';

function Probe({ name, path, load }: { name: string; path: string; load: () => Promise<{ status: string; database?: string }> }) {
  const probe = useAsync(load, name);
  const ok = probe.data?.status === 'ok';
  return (
    <li className="probe">
      <div>
        <strong>{name}</strong> <span className="mono muted small">{path}</span>
      </div>
      <div>
        {probe.loading ? (
          <Badge>checking…</Badge>
        ) : probe.error ? (
          <Badge tone="bad">✗ down</Badge>
        ) : (
          <Badge tone={ok ? 'good' : 'bad'}>
            {ok ? '✓' : '✗'} {probe.data?.status}
            {probe.data?.database ? ` · db ${probe.data.database}` : ''}
          </Badge>
        )}{' '}
        <button type="button" className="btn btn-small" onClick={probe.reload}>
          Recheck
        </button>
      </div>
    </li>
  );
}

export function SystemPage() {
  return (
    <div className="page">
      <div className="page-header">
        <h1>System Observability</h1>
      </div>
      <Card title="Service probes">
        <ul className="probe-list">
          <Probe name="Liveness" path="/healthz" load={system.healthz} />
          <Probe name="Readiness" path="/readyz" load={system.readyz} />
        </ul>
      </Card>
      <Card title="Dashboards & tools">
        <ul className="link-list">
          <li>
            <a href={GRAFANA_URL} target="_blank" rel="noreferrer">
              Grafana ↗
            </a>
            <span className="muted small">Experiment and service dashboards (assignment rate, latency, errors).</span>
          </li>
          <li>
            <a href={PROMETHEUS_URL} target="_blank" rel="noreferrer">
              Prometheus ↗
            </a>
            <span className="muted small">Raw metrics and alert rules.</span>
          </li>
          <li>
            <a href="/metrics" target="_blank" rel="noreferrer">
              /metrics ↗
            </a>
            <span className="muted small">This API’s Prometheus scrape endpoint.</span>
          </li>
          <li>
            <a href="/api/docs/" target="_blank" rel="noreferrer">
              API docs ↗
            </a>
            <span className="muted small">OpenAPI / Swagger UI.</span>
          </li>
        </ul>
        <ErrorBox error={null} />
      </Card>
    </div>
  );
}
