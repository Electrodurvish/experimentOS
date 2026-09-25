import { experiments, type Experiment, type ExperimentResults, type ExperimentStatus } from '../api';
import { useAuth } from '../auth/context';
import { bpToPct, formatLift, formatRate, healthTone, typeLabel } from '../lib/format';
import { splitArms } from '../lib/results';
import { useAction } from '../lib/useAsync';
import { ErrorBox, HealthBadge, StatusBadge } from './ui';

const TRANSITION_LABELS: Partial<Record<ExperimentStatus, string>> = {
  REVIEW: 'Submit for review',
  APPROVED: 'Approve',
  RUNNING: 'Start',
  PAUSED: 'Pause',
  COMPLETED: 'Complete',
  ARCHIVED: 'Archive',
  DRAFT: 'Back to draft',
};

/** The overview card from the plan's mockup: key, status, rollout %, health, control vs treatment, lift. */
export function ExperimentHeader({
  experiment,
  results,
  healthScore,
  healthLoading,
  onChanged,
}: {
  experiment: Experiment;
  results?: ExperimentResults;
  healthScore?: number;
  healthLoading?: boolean;
  onChanged?: (e: Experiment) => void;
}) {
  const { canEdit } = useAuth();
  const arms = splitArms(results, experiment);
  const transition = useAction(async (status: ExperimentStatus) => {
    if (status === 'RUNNING') return experiments.start(experiment.id);
    if (status === 'PAUSED') {
      const reason = window.prompt('Reason for pausing (optional):') ?? undefined;
      return experiments.pause(experiment.id, reason || undefined);
    }
    return experiments.transition(experiment.id, status);
  });

  async function onTransition(status: ExperimentStatus) {
    if ((status === 'COMPLETED' || status === 'ARCHIVED') && !window.confirm(`Move ${experiment.key} to ${status}?`)) return;
    const updated = await transition.run(status);
    if (updated && onChanged) onChanged(updated);
  }

  const lift = arms.treatment?.result.lift;
  return (
    <section className="card exp-header" aria-label="Experiment overview">
      <div className="exp-header-top">
        <div className="exp-header-id">
          <h1 className="mono exp-header-key">{experiment.key}</h1>
          <div className="muted">{experiment.name}</div>
          <div className="exp-header-meta">
            <StatusBadge status={experiment.status} />
            <span className="muted small">{typeLabel(experiment.experiment_type)}</span>
          </div>
        </div>
        <div className="exp-header-rollout" aria-label="Rollout percentage">
          <span className="exp-header-rollout-value">{bpToPct(experiment.rollout_percentage)}</span>
          <span className="muted small">rollout</span>
        </div>
      </div>

      <div className="exp-header-body">
        <div className={`exp-header-health tone-${healthTone(healthScore)}`}>
          <span className="muted small">Health score</span>
          {healthLoading && healthScore === undefined ? <HealthBadge loading /> : <strong>{healthScore !== undefined ? `${healthScore}/100` : '—'}</strong>}
        </div>
        <div className="exp-header-arms">
          <div>
            <span className="muted small">Control{arms.control ? ` · ${arms.control.key}` : ''}</span>
            <strong>{formatRate(arms.control?.result.conversion_rate)}</strong>
          </div>
          <div>
            <span className="muted small">Treatment{arms.treatment ? ` · ${arms.treatment.key}` : ''}</span>
            <strong>{formatRate(arms.treatment?.result.conversion_rate)}</strong>
          </div>
          <div>
            <span className="muted small">Lift</span>
            <strong className={lift === undefined ? '' : lift >= 0 ? 'pos' : 'neg'}>{formatLift(lift)}</strong>
            {arms.treatment?.result.is_significant !== undefined && (
              <span className="muted small">{arms.treatment.result.is_significant ? 'significant' : 'not significant'}</span>
            )}
          </div>
        </div>
      </div>

      {canEdit && experiment.allowed_transitions.length > 0 && (
        <div className="exp-header-actions">
          {experiment.allowed_transitions.map((s) => (
            <button
              key={s}
              type="button"
              className={`btn btn-small ${s === 'RUNNING' ? 'btn-primary' : s === 'PAUSED' ? 'btn-warn' : ''}`}
              disabled={transition.busy}
              onClick={() => onTransition(s)}
            >
              {experiment.status === 'PAUSED' && s === 'RUNNING' ? 'Resume' : (TRANSITION_LABELS[s] ?? s)}
            </button>
          ))}
        </div>
      )}
      <ErrorBox error={transition.error} />
    </section>
  );
}
