import { experiments, type Experiment } from '../../api';
import { Card, ErrorBox, HealthBadge, Loading } from '../../components/ui';
import { healthTone, humanize } from '../../lib/format';
import { useAsync } from '../../lib/useAsync';

export function HealthTab({ experiment }: { experiment: Experiment }) {
  const health = useAsync(() => experiments.health(experiment.id), `health-${experiment.id}`);
  const srm = useAsync(() => experiments.srm(experiment.id), `srm-${experiment.id}`);
  const h = health.data?.health;

  return (
    <div className="stack">
      <Card title="Health score" actions={h && <HealthBadge score={h.overall_score} />}>
        {health.loading && <Loading />}
        <ErrorBox error={health.error} onRetry={health.reload} />
        {h && (
          <>
            <div className={`health-hero tone-${healthTone(h.overall_score)}`}>
              <span className="health-hero-value">{h.overall_score}</span>
              <span className="muted">/ 100</span>
            </div>
            <ul className="dimension-list">
              {Object.entries(h.dimensions).map(([name, d]) => (
                <li key={name}>
                  <div className="dimension-head">
                    <span>{humanize(name)}</span>
                    <span className="mono">{d.score}</span>
                  </div>
                  <div className="meter" role="meter" aria-valuemin={0} aria-valuemax={100} aria-valuenow={d.score} aria-label={humanize(name)}>
                    <div className={`meter-fill tone-${healthTone(d.score)}`} style={{ width: `${Math.max(0, Math.min(100, d.score))}%` }} />
                  </div>
                  <div className="muted small">{d.detail}</div>
                </li>
              ))}
            </ul>
          </>
        )}
      </Card>
      <Card title="Sample ratio check">
        {srm.loading && <Loading />}
        <ErrorBox error={srm.error} onRetry={srm.reload} />
        {srm.data && (
          <div className={`notice ${srm.data.is_mismatch ? 'notice-error' : 'notice-good'}`}>
            {srm.data.is_mismatch ? '✗ ' : srm.data.is_mismatch === false ? '✓ ' : ''}
            {srm.data.message}
            {srm.data.p_value !== undefined && <span className="muted small"> (p = {srm.data.p_value.toFixed(4)})</span>}
          </div>
        )}
      </Card>
    </div>
  );
}
