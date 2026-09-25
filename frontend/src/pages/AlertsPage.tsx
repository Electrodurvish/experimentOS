import { useState } from 'react';
import { Link } from 'react-router-dom';
import { experiments, fetchAllPages } from '../api';
import { Badge, Card, Empty, ErrorBox, Loading } from '../components/ui';
import { collectAlerts, sortAlerts, type AlertItem } from '../lib/alerts';
import { formatDateTime } from '../lib/format';
import { useAsync } from '../lib/useAsync';

export function AlertsPage() {
  const [filter, setFilter] = useState<'all' | 'critical' | 'warning'>('all');
  const alerts = useAsync(async () => {
    const [running, paused] = await Promise.all([
      fetchAllPages((page) => experiments.list({ status: 'RUNNING', page, page_size: 100 }), 5),
      fetchAllPages((page) => experiments.list({ status: 'PAUSED', page, page_size: 100 }), 5),
    ]);
    const list = [...running, ...paused];
    const failures: string[] = [];
    const perExperiment = await Promise.all(
      list.map(async (e) => {
        const [decisions, timeline] = await Promise.all([
          experiments.decisions(e.id, 1, 100).then((d) => d.results, () => (failures.push(e.key), [])),
          experiments.timeline(e.id).then((t) => t.timeline, () => (failures.push(e.key), [])),
        ]);
        return collectAlerts(e.id, e.key, decisions, timeline);
      }),
    );
    return { items: sortAlerts(perExperiment.flat()), scanned: list.length, failures: [...new Set(failures)] };
  }, 'alerts');

  const items: AlertItem[] = (alerts.data?.items ?? []).filter((a) => filter === 'all' || a.severity === filter);

  return (
    <div className="page">
      <div className="page-header">
        <h1>Alerts</h1>
        <button type="button" className="btn" onClick={alerts.reload}>
          Refresh
        </button>
      </div>
      <p className="muted">
        Recent decisions recommending pause, rollback or decreased rollout, plus rollback, guardrail-breach and anomaly events across running
        and paused experiments.
      </p>
      <div className="segmented" role="tablist">
        {(['all', 'critical', 'warning'] as const).map((f) => (
          <button key={f} type="button" role="tab" aria-selected={filter === f} className={filter === f ? 'active' : ''} onClick={() => setFilter(f)}>
            {f}
          </button>
        ))}
      </div>
      <Card>
        {alerts.loading && <Loading label="Scanning experiments…" />}
        <ErrorBox error={alerts.error} onRetry={alerts.reload} />
        {alerts.data && alerts.data.failures.length > 0 && (
          <div className="notice notice-warn">Couldn’t load some data for: {alerts.data.failures.join(', ')}.</div>
        )}
        {alerts.data && items.length === 0 && <Empty>✓ No alerts across {alerts.data.scanned} live experiment(s).</Empty>}
        <ul className="alert-list">
          {items.map((a) => (
            <li key={a.id} className={`alert-item tone-${a.severity === 'critical' ? 'bad' : 'warn'}`}>
              <div className="alert-head">
                <Badge tone={a.severity === 'critical' ? 'bad' : 'warn'}>{a.severity}</Badge>
                <strong>{a.title}</strong>
                <Link to={`/experiments/${a.experimentId}?tab=${a.kind === 'decision' ? 'decision' : 'timeline'}`} className="mono small">
                  {a.experimentKey}
                </Link>
              </div>
              {a.detail && <div className="small">{a.detail}</div>}
              <div className="muted small">{formatDateTime(a.createdAt)}</div>
            </li>
          ))}
        </ul>
      </Card>
    </div>
  );
}
