import { useEffect, useState, type FormEvent } from 'react';
import {
  experiments,
  GUARDRAIL_OPERATOR_LABELS,
  GUARDRAIL_OPERATORS,
  type Experiment,
  type Guardrail,
  type GuardrailInput,
  type RolloutPolicy,
} from '../api';
import { useAuth } from '../auth/context';
import { bpToPct, formatDateTime, humanize, pctToBp } from '../lib/format';
import { parseStages } from '../lib/rollout';
import { useAction, useAsync } from '../lib/useAsync';
import { RolloutBar } from './RolloutBar';
import { Badge, Card, Empty, ErrorBox, Field, Loading } from './ui';

export function RolloutPanel({ experiment, onChanged }: { experiment: Experiment; onChanged: () => void }) {
  const { canEdit } = useAuth();
  const id = experiment.id;
  const rollout = useAsync(() => experiments.rollout(id), `rollout-${id}`);
  const policy = useAsync(() => experiments.rolloutPolicy(id), `policy-${id}`);
  const [reason, setReason] = useState('');
  const [custom, setCustom] = useState('');
  const [rollbackTo, setRollbackTo] = useState('');
  const [rollbackReason, setRollbackReason] = useState('');
  const setRollout = useAction(experiments.setRollout);
  const rollback = useAction(experiments.rollback);
  const [message, setMessage] = useState<string | null>(null);

  const current = rollout.data?.rollout_percentage ?? experiment.rollout_percentage;
  const stages = policy.data?.stages ?? rollout.data?.policy.stages ?? [];
  const defaultRollback = policy.data?.rollback_percentage ?? rollout.data?.policy.rollback_percentage;

  function refresh() {
    rollout.reload();
    onChanged();
  }

  async function moveTo(bp: number) {
    if (!reason.trim()) {
      setMessage('Enter a reason before changing the rollout.');
      return;
    }
    const res = await setRollout.run(id, bp, reason.trim());
    if (res) {
      setMessage(res.detail ?? `Rollout moved to ${bpToPct(bp)}.`);
      setReason('');
      setCustom('');
      refresh();
    }
  }

  async function doRollback(e: FormEvent) {
    e.preventDefault();
    let to: number | undefined;
    if (rollbackTo.trim()) {
      const bp = pctToBp(rollbackTo);
      if (bp === null) {
        setMessage('Rollback target must be a percentage between 0 and 100.');
        return;
      }
      to = bp;
    }
    const target = to ?? defaultRollback;
    if (!window.confirm(`Roll back ${experiment.key} from ${bpToPct(current)} to ${bpToPct(target)}?`)) return;
    const res = await rollback.run(id, rollbackReason.trim() || 'Manual rollback', to);
    if (res) {
      setMessage(`Rolled back to ${bpToPct(target)}.`);
      setRollbackReason('');
      setRollbackTo('');
      refresh();
    }
  }

  return (
    <div className="stack">
      <Card title="Current rollout">
        <div className="rollout-hero">
          <span className="rollout-hero-value">{bpToPct(current)}</span>
          <span className="muted">of eligible traffic</span>
        </div>
        <RolloutBar bp={current} label={false} />
        {experiment.status !== 'RUNNING' && (
          <p className="muted small">Experiment is {experiment.status}; rollout changes take effect while it is running.</p>
        )}
        {message && (
          <div className="notice notice-info" role="status">
            {message}
          </div>
        )}
        <ErrorBox error={setRollout.error ?? rollback.error} />
        {canEdit && (
          <>
            <h3 className="subhead">Change stage</h3>
            <Field label="Reason (required)" htmlFor="rollout-reason">
              <input id="rollout-reason" value={reason} maxLength={255} placeholder="Metrics healthy at current stage" onChange={(e) => setReason(e.target.value)} />
            </Field>
            <div className="stage-buttons">
              {stages.map((s) => (
                <button
                  key={s}
                  type="button"
                  className={`btn ${s === current ? 'btn-primary' : ''}`}
                  disabled={s === current || setRollout.busy}
                  aria-pressed={s === current}
                  onClick={() => moveTo(s)}
                >
                  {bpToPct(s)}
                </button>
              ))}
              <span className="stage-custom">
                <input
                  aria-label="Custom rollout percent"
                  inputMode="decimal"
                  placeholder="custom %"
                  value={custom}
                  onChange={(e) => setCustom(e.target.value)}
                />
                <button
                  type="button"
                  className="btn"
                  disabled={setRollout.busy || pctToBp(custom) === null}
                  onClick={() => {
                    const bp = pctToBp(custom);
                    if (bp !== null) void moveTo(bp);
                  }}
                >
                  Set
                </button>
              </span>
            </div>

            <h3 className="subhead">Rollback</h3>
            <form className="rollback-form" onSubmit={doRollback}>
              <input
                aria-label="Rollback to percent"
                inputMode="decimal"
                placeholder={`to % (default ${bpToPct(defaultRollback)})`}
                value={rollbackTo}
                onChange={(e) => setRollbackTo(e.target.value)}
              />
              <input
                aria-label="Rollback reason"
                placeholder="Reason"
                maxLength={255}
                value={rollbackReason}
                onChange={(e) => setRollbackReason(e.target.value)}
              />
              <button type="submit" className="btn btn-danger" disabled={rollback.busy || current === 0}>
                Roll back
              </button>
            </form>
          </>
        )}
      </Card>

      <Card title="Rollout history">
        {rollout.loading && <Loading />}
        <ErrorBox error={rollout.error} onRetry={rollout.reload} />
        {rollout.data && rollout.data.history.length === 0 && <Empty>No rollout changes yet.</Empty>}
        {rollout.data && rollout.data.history.length > 0 && (
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th>When</th>
                  <th>Change</th>
                  <th>Action</th>
                  <th className="hide-sm">Reason</th>
                </tr>
              </thead>
              <tbody>
                {rollout.data.history.map((h) => (
                  <tr key={h.id}>
                    <td className="small">{formatDateTime(h.created_at)}</td>
                    <td className="mono">
                      {bpToPct(h.from_percentage)} → {bpToPct(h.to_percentage)}
                    </td>
                    <td>
                      <Badge tone={h.action === 'rollback' ? 'bad' : h.action === 'decrease' ? 'warn' : 'info'}>{h.action}</Badge>{' '}
                      {h.automated && <Badge>auto</Badge>}
                    </td>
                    <td className="hide-sm small">{h.reason}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      <PolicyEditor id={id} policy={policy.data} loading={policy.loading} error={policy.error} onSaved={(p) => { policy.setData(p); rollout.reload(); }} canEdit={canEdit} />
      <GuardrailEditor id={id} canEdit={canEdit} />
    </div>
  );
}

function PolicyEditor({
  id,
  policy,
  loading,
  error,
  onSaved,
  canEdit,
}: {
  id: string;
  policy?: RolloutPolicy;
  loading: boolean;
  error: unknown;
  onSaved: (p: RolloutPolicy) => void;
  canEdit: boolean;
}) {
  const [stagesText, setStagesText] = useState('');
  const [draft, setDraft] = useState<RolloutPolicy | null>(null);
  const [saved, setSaved] = useState(false);
  const save = useAction(experiments.updateRolloutPolicy);

  useEffect(() => {
    if (policy) {
      setDraft(policy);
      setStagesText(policy.stages.map((s) => s / 100).join(', '));
    }
  }, [policy]);

  const parsed = parseStages(stagesText);

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!draft || parsed.error) return;
    setSaved(false);
    const res = await save.run(id, {
      stages: parsed.stages,
      auto_advance: draft.auto_advance,
      auto_rollback: draft.auto_rollback,
      rollback_percentage: draft.rollback_percentage,
      min_health_score: draft.min_health_score,
      min_stage_duration_minutes: draft.min_stage_duration_minutes,
      min_confidence: draft.min_confidence,
    });
    if (res) {
      onSaved(res);
      setSaved(true);
    }
  }

  return (
    <Card title="Rollout policy">
      {loading && <Loading />}
      <ErrorBox error={error} />
      {draft && (
        <form onSubmit={submit}>
          <fieldset disabled={!canEdit} className="plain-fieldset">
            <div className="form-grid">
              <Field label="Stages (%)" htmlFor="stages" hint={parsed.error ?? parsed.stages.map((s) => bpToPct(s)).join(' → ')}>
                <input id="stages" className={parsed.error ? 'invalid' : undefined} value={stagesText} onChange={(e) => setStagesText(e.target.value)} />
              </Field>
              <Field label="Rollback to (%)" htmlFor="rb">
                <input
                  id="rb"
                  type="number"
                  min={0}
                  max={100}
                  step={0.01}
                  value={draft.rollback_percentage / 100}
                  onChange={(e) => setDraft({ ...draft, rollback_percentage: pctToBp(e.target.value) ?? 0 })}
                />
              </Field>
              <Field label="Min health score" htmlFor="mh">
                <input id="mh" type="number" min={0} max={100} value={draft.min_health_score} onChange={(e) => setDraft({ ...draft, min_health_score: Number(e.target.value) })} />
              </Field>
              <Field label="Min stage duration (min)" htmlFor="md">
                <input
                  id="md"
                  type="number"
                  min={0}
                  value={draft.min_stage_duration_minutes}
                  onChange={(e) => setDraft({ ...draft, min_stage_duration_minutes: Number(e.target.value) })}
                />
              </Field>
              <Field label="Min confidence (%)" htmlFor="mc" hint="Automatic actions require at least this decision confidence.">
                <input
                  id="mc"
                  type="number"
                  min={0}
                  max={100}
                  value={Math.round(draft.min_confidence * 100)}
                  onChange={(e) => setDraft({ ...draft, min_confidence: Number(e.target.value) / 100 })}
                />
              </Field>
            </div>
            <label className="checkbox">
              <input type="checkbox" checked={draft.auto_advance} onChange={(e) => setDraft({ ...draft, auto_advance: e.target.checked })} /> Auto-advance to the next
              stage when recommended
            </label>
            <label className="checkbox">
              <input type="checkbox" checked={draft.auto_rollback} onChange={(e) => setDraft({ ...draft, auto_rollback: e.target.checked })} /> Auto-rollback / pause on
              guardrail breach
            </label>
            <ErrorBox error={save.error} />
            {saved && <div className="notice notice-good">✓ Policy saved.</div>}
            {canEdit && (
              <div className="form-actions">
                <button type="submit" className="btn btn-primary" disabled={save.busy || !!parsed.error}>
                  Save policy
                </button>
              </div>
            )}
          </fieldset>
        </form>
      )}
    </Card>
  );
}

const EMPTY_GUARDRAIL: GuardrailInput = {
  name: '',
  metric_name: '',
  source: 'TELEMETRY',
  operator: 'RELATIVE_INCREASE_GT',
  threshold: 20,
  action: 'ROLLBACK',
  is_active: true,
};

function GuardrailEditor({ id, canEdit }: { id: string; canEdit: boolean }) {
  const list = useAsync(() => experiments.guardrails(id), `guardrails-${id}`);
  const [draft, setDraft] = useState<GuardrailInput>(EMPTY_GUARDRAIL);
  const create = useAction(experiments.createGuardrail);
  const update = useAction(experiments.updateGuardrail);
  const remove = useAction(experiments.deleteGuardrail);

  async function add(e: FormEvent) {
    e.preventDefault();
    if (!draft.name.trim() || !draft.metric_name.trim()) return;
    const g = await create.run(id, { ...draft, name: draft.name.trim(), metric_name: draft.metric_name.trim() });
    if (g) {
      setDraft(EMPTY_GUARDRAIL);
      list.reload();
    }
  }

  async function toggle(g: Guardrail) {
    if (await update.run(id, g.id, { is_active: !g.is_active })) list.reload();
  }

  async function del(g: Guardrail) {
    if (!window.confirm(`Delete guardrail "${g.name}"?`)) return;
    await remove.run(id, g.id);
    list.reload();
  }

  const relative = draft.operator.startsWith('RELATIVE');

  return (
    <Card title="Guardrails">
      {list.loading && <Loading />}
      <ErrorBox error={list.error ?? update.error ?? remove.error} onRetry={list.reload} />
      {list.data && list.data.length === 0 && <Empty>No guardrails. Add one to auto-pause or roll back on regressions.</Empty>}
      {list.data && list.data.length > 0 && (
        <ul className="guardrail-list">
          {list.data.map((g) => (
            <li key={g.id} className={g.is_active ? '' : 'inactive'}>
              <div>
                <strong>{g.name}</strong> <Badge tone={g.action === 'ROLLBACK' ? 'bad' : 'warn'}>{g.action}</Badge>{' '}
                {!g.is_active && <Badge>inactive</Badge>}
                <div className="muted small">
                  <span className="mono">{g.metric_name}</span> ({humanize(g.source)}) — {GUARDRAIL_OPERATOR_LABELS[g.operator] ?? g.operator} {g.threshold}
                </div>
              </div>
              {canEdit && (
                <div className="button-row">
                  <button type="button" className="btn btn-small" onClick={() => toggle(g)}>
                    {g.is_active ? 'Disable' : 'Enable'}
                  </button>
                  <button type="button" className="btn btn-small btn-danger-ghost" onClick={() => del(g)}>
                    Delete
                  </button>
                </div>
              )}
            </li>
          ))}
        </ul>
      )}
      {canEdit && (
        <form className="guardrail-form" onSubmit={add}>
          <h3 className="subhead">Add guardrail</h3>
          <div className="form-grid">
            <Field label="Name" htmlFor="g-name">
              <input id="g-name" required value={draft.name} placeholder="Error rate" onChange={(e) => setDraft({ ...draft, name: e.target.value })} />
            </Field>
            <Field label="Metric" htmlFor="g-metric">
              <input id="g-metric" required className="mono" value={draft.metric_name} placeholder="error_rate" onChange={(e) => setDraft({ ...draft, metric_name: e.target.value })} />
            </Field>
            <Field label="Source" htmlFor="g-source">
              <select id="g-source" value={draft.source} onChange={(e) => setDraft({ ...draft, source: e.target.value as GuardrailInput['source'] })}>
                <option value="TELEMETRY">Production telemetry</option>
                <option value="CONVERSION">Conversion metric</option>
              </select>
            </Field>
            <Field label="Operator" htmlFor="g-op">
              <select id="g-op" value={draft.operator} onChange={(e) => setDraft({ ...draft, operator: e.target.value as GuardrailInput['operator'] })}>
                {GUARDRAIL_OPERATORS.map((o) => (
                  <option key={o} value={o}>
                    {GUARDRAIL_OPERATOR_LABELS[o]}
                  </option>
                ))}
              </select>
            </Field>
            <Field label={relative ? 'Threshold (%)' : 'Threshold'} htmlFor="g-th">
              <input id="g-th" type="number" step="any" value={draft.threshold} onChange={(e) => setDraft({ ...draft, threshold: Number(e.target.value) })} />
            </Field>
            <Field label="Action" htmlFor="g-action">
              <select id="g-action" value={draft.action} onChange={(e) => setDraft({ ...draft, action: e.target.value as GuardrailInput['action'] })}>
                <option value="ROLLBACK">Rollback</option>
                <option value="PAUSE">Pause</option>
              </select>
            </Field>
          </div>
          <ErrorBox error={create.error} />
          <div className="form-actions">
            <button type="submit" className="btn btn-primary" disabled={create.busy}>
              Add guardrail
            </button>
          </div>
        </form>
      )}
    </Card>
  );
}
