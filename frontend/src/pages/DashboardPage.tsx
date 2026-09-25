import { Link } from 'react-router-dom';
import { EXPERIMENT_STATUSES, experiments, type Experiment, type ExperimentStatus } from '../api';
import { useAuth } from '../auth/context';
import { RolloutBar } from '../components/RolloutBar';
import { Card, Empty, ErrorBox, HealthBadge, Loading, StatusBadge } from '../components/ui';
import { formatDateTime } from '../lib/format';
import { useAsync } from '../lib/useAsync';
import { useHealthScores } from '../lib/useHealthScores';

const COUNTED: ExperimentStatus[] = ['RUNNING', 'PAUSED', 'REVIEW', 'DRAFT', 'COMPLETED'];

export function DashboardPage() {
  const { canEdit } = useAuth();
  const running = useAsync(() => experiments.list({ status: 'RUNNING' }), 'running');
  const paused = useAsync(() => experiments.list({ status: 'PAUSED' }), 'paused');
  const counts = useAsync(async () => {
    const entries = await Promise.all(
      COUNTED.map(async (s) => [s, (await experiments.list({ status: s })).count] as const),
    );
    return Object.fromEntries(entries) as Record<ExperimentStatus, number>;
  }, 'counts');

  const live: Experiment[] = [...(running.data?.results ?? []), ...(paused.data?.results ?? [])];
  const { scores, loading: healthLoading } = useHealthScores(live.map((e) => e.id));

  return (
    <div className="page">
      <div className="page-header">
        <h1>Dashboard</h1>
        {canEdit && (
          <Link to="/experiments/new" className="btn btn-primary">
            New experiment
          </Link>
        )}
      </div>

      <div className="stat-row">
        {COUNTED.map((s) => (
          <Link key={s} to={`/experiments?status=${s}`} className="stat stat-link">
            <div className="stat-label">{s.toLowerCase()}</div>
            <div className="stat-value">{counts.data ? counts.data[s] : '…'}</div>
          </Link>
        ))}
      </div>
      <ErrorBox error={counts.error} onRetry={counts.reload} />

      <Card title="Live experiments" actions={<Link to="/experiments?status=RUNNING">View all</Link>}>
        {(running.loading || paused.loading) && <Loading />}
        <ErrorBox error={running.error ?? paused.error} onRetry={running.reload} />
        {!running.loading && !paused.loading && live.length === 0 && (
          <Empty>
            No running or paused experiments. <Link to="/experiments">Browse experiments</Link> or{' '}
            {canEdit ? <Link to="/experiments/new">create one</Link> : 'ask a manager to create one'}.
          </Empty>
        )}
        <div className="exp-grid">
          {live.map((e) => (
            <Link key={e.id} to={`/experiments/${e.id}`} className="exp-tile">
              <div className="exp-tile-head">
                <span className="mono exp-key">{e.key}</span>
                <StatusBadge status={e.status} />
              </div>
              <div className="exp-tile-name">{e.name}</div>
              <RolloutBar bp={e.rollout_percentage} />
              <div className="exp-tile-foot">
                <HealthBadge score={scores[e.id]} loading={healthLoading && !(e.id in scores)} />
                <span className="muted small">since {formatDateTime(e.started_at)}</span>
              </div>
            </Link>
          ))}
        </div>
      </Card>
      <p className="muted small">
        Statuses tracked: {EXPERIMENT_STATUSES.join(' → ')}.
      </p>
    </div>
  );
}
