import { useState } from 'react';
import { experiments, type Decision, type Experiment } from '../../api';
import { useAuth } from '../../auth/context';
import { ChecksList, EvidenceList } from '../../components/Evidence';
import { Badge, Card, Empty, ErrorBox, Loading, Pagination } from '../../components/ui';
import { bpToPct, formatDateTime, humanize, recommendationTone } from '../../lib/format';
import { useAction, useAsync } from '../../lib/useAsync';

export function DecisionTab({ experiment, onChanged }: { experiment: Experiment; onChanged: () => void }) {
  const { canEdit } = useAuth();
  const preview = useAsync(() => experiments.decisionPreview(experiment.id), `decision-${experiment.id}`);
  const [page, setPage] = useState(1);
  const history = useAsync(() => experiments.decisions(experiment.id, page), `decisions-${experiment.id}-${page}`);
  const decide = useAction(experiments.decide);
  const [last, setLast] = useState<Decision | null>(null);
  const p = preview.data;

  async function run(apply: boolean) {
    if (apply && !window.confirm(`Apply "${humanize(p?.recommendation)}" to ${experiment.key}? This may change its rollout or status.`)) return;
    const d = await decide.run(experiment.id, apply);
    if (d) {
      setLast(d);
      history.reload();
      preview.reload();
      if (apply) onChanged();
    }
  }

  return (
    <div className="stack">
      <Card
        title="Recommendation"
        actions={
          <button type="button" className="btn btn-small" onClick={preview.reload}>
            Refresh
          </button>
        }
      >
        {preview.loading && <Loading label="Evaluating…" />}
        <ErrorBox error={preview.error} onRetry={preview.reload} />
        {p && (
          <div className="stack-sm">
            <div className="decision-head">
              <Badge tone={recommendationTone(p.recommendation)}>{humanize(p.recommendation)}</Badge>
              <span>
                Confidence <strong>{p.confidence_label}</strong> <span className="muted">({Math.round(p.confidence * 100)}%)</span>
              </span>
              {p.target_percentage !== null && p.target_percentage !== undefined && (
                <span>
                  Rollout {bpToPct(p.rollout_percentage)} → <strong>{bpToPct(p.target_percentage)}</strong>
                </span>
              )}
            </div>
            <p className="lead">{p.summary}</p>
            <h3 className="subhead">Evidence</h3>
            <EvidenceList evidence={p.evidence} />
            <h3 className="subhead">Checks</h3>
            <ChecksList checks={p.checks} />
            {canEdit && (
              <div className="button-row">
                <button type="button" className="btn" disabled={decide.busy} onClick={() => run(false)}>
                  Record decision
                </button>
                <button type="button" className="btn btn-primary" disabled={decide.busy} onClick={() => run(true)}>
                  Record &amp; apply
                </button>
              </div>
            )}
            <ErrorBox error={decide.error} />
            {last && (
              <div className="notice notice-good">
                Decision recorded: {humanize(last.recommendation)}
                {last.applied ? ` — applied (${humanize(last.applied_action)})` : ' — not applied'}.
              </div>
            )}
          </div>
        )}
      </Card>

      <Card title="Decision history">
        {history.loading && <Loading />}
        <ErrorBox error={history.error} onRetry={history.reload} />
        {history.data && history.data.results.length === 0 && <Empty>No decisions recorded yet.</Empty>}
        <ul className="history-list">
          {history.data?.results.map((d) => (
            <li key={d.id}>
              <details>
                <summary>
                  <Badge tone={recommendationTone(d.recommendation)}>{humanize(d.recommendation)}</Badge>{' '}
                  <span className="muted small">
                    {formatDateTime(d.created_at)} · {d.confidence_label} · {humanize(d.triggered_by)}
                    {d.applied_action && d.applied_action !== 'none' ? ` · applied ${humanize(d.applied_action)}` : ''}
                    {d.from_percentage !== null && d.to_percentage !== null ? ` · ${bpToPct(d.from_percentage)} → ${bpToPct(d.to_percentage)}` : ''}
                  </span>
                </summary>
                <p>{d.summary}</p>
                <EvidenceList evidence={d.evidence ?? []} />
                <ChecksList checks={d.checks ?? []} />
              </details>
            </li>
          ))}
        </ul>
        {history.data && <Pagination page={page} count={history.data.count} onPage={setPage} />}
      </Card>
    </div>
  );
}
