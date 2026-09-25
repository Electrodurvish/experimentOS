import { useState, type FormEvent } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import {
  engine,
  experiments,
  projects,
  type DebugResponse,
  type DebugStep,
  type EvaluationResult,
  type UserAssignmentsResponse,
  type UserDebugResponse,
} from '../api';
import { Badge, Card, Empty, ErrorBox, Field, StatusBadge } from '../components/ui';
import { VersionConfigView } from '../components/VersionConfigView';
import { parseContext, parseExplanationLine } from '../lib/debug';
import { bpToPct, formatDateTime, humanize } from '../lib/format';
import { useAction, useAsync } from '../lib/useAsync';

type Mode = 'user' | 'assignments' | 'replay';
const MODES: { id: Mode; label: string }[] = [
  { id: 'user', label: 'Explain a user' },
  { id: 'assignments', label: 'User assignments' },
  { id: 'replay', label: 'Replay by key' },
];

export function DebuggerPage() {
  const [params, setParams] = useSearchParams();
  const mode = (MODES.find((m) => m.id === params.get('mode'))?.id ?? 'user') as Mode;
  const userId = params.get('user') ?? '';
  const experimentId = params.get('experiment') ?? '';

  function update(next: Record<string, string>) {
    const p = new URLSearchParams(params);
    for (const [k, v] of Object.entries(next)) {
      if (v) p.set(k, v);
      else p.delete(k);
    }
    setParams(p, { replace: true });
  }

  return (
    <div className="page">
      <div className="page-header">
        <h1>Assignment Debugger</h1>
      </div>
      <div className="segmented" role="tablist" aria-label="Debugger mode">
        {MODES.map((m) => (
          <button key={m.id} type="button" role="tab" aria-selected={mode === m.id} className={mode === m.id ? 'active' : ''} onClick={() => update({ mode: m.id })}>
            {m.label}
          </button>
        ))}
      </div>
      {mode === 'user' && (
        <UserDebug
          key={`${experimentId}|${userId}`}
          initialUser={userId}
          initialExperiment={experimentId}
          onSelect={(exp, user) => update({ experiment: exp, user })}
        />
      )}
      {mode === 'assignments' && (
        <UserAssignments
          initialUser={userId}
          onUser={(user) => update({ user })}
          onExplain={(exp, user) => update({ mode: 'user', experiment: exp, user })}
        />
      )}
      {mode === 'replay' && <ReplayByKey />}
    </div>
  );
}

// ---------------------------------------------------------------------------

function UserDebug({
  initialUser,
  initialExperiment,
  onSelect,
}: {
  initialUser: string;
  initialExperiment: string;
  onSelect: (experimentId: string, userId: string) => void;
}) {
  const expList = useAsync(() => experiments.list({ page_size: 100, ordering: '-updated_at' }), 'dbg-exps');
  const [experimentId, setExperimentId] = useState(initialExperiment);
  const [userId, setUserId] = useState(initialUser);
  const [contextText, setContextText] = useState('');
  const [contextError, setContextError] = useState<string | null>(null);
  const [data, setData] = useState<UserDebugResponse | null>(null);
  const run = useAction(experiments.userDebug);

  async function submit(e: FormEvent) {
    e.preventDefault();
    const ctx = parseContext(contextText);
    setContextError(ctx.error ?? null);
    if (ctx.error || !experimentId || !userId.trim()) return;
    onSelect(experimentId, userId.trim());
    setData((await run.run(experimentId, userId.trim(), ctx.value)) ?? null);
  }

  return (
    <>
      <Card>
        <form onSubmit={submit}>
          <div className="form-grid">
            <Field label="Experiment" htmlFor="ud-exp">
              <select id="ud-exp" required value={experimentId} onChange={(e) => setExperimentId(e.target.value)}>
                <option value="">Select…</option>
                {expList.data?.results.map((x) => (
                  <option key={x.id} value={x.id}>
                    {x.key} · {x.status}
                  </option>
                ))}
              </select>
            </Field>
            <Field label="User ID" htmlFor="ud-user">
              <input id="ud-user" className="mono" required value={userId} placeholder="user_123" onChange={(e) => setUserId(e.target.value)} />
            </Field>
          </div>
          <Field
            label="Context (JSON, optional)"
            htmlFor="ud-ctx"
            hint={contextError ?? 'Leave empty to reuse the context recorded with the user’s last assignment.'}
          >
            <textarea
              id="ud-ctx"
              className={`mono ${contextError ? 'invalid' : ''}`}
              rows={3}
              placeholder='{"country": "IN"}'
              value={contextText}
              onChange={(e) => setContextText(e.target.value)}
            />
          </Field>
          <div className="form-actions">
            <button type="submit" className="btn btn-primary" disabled={run.busy || !experimentId || !userId.trim()}>
              {run.busy ? 'Explaining…' : 'Explain assignment'}
            </button>
          </div>
        </form>
        <ErrorBox error={expList.error} onRetry={expList.reload} />
        <ErrorBox error={run.error} feature="Per-user debugging" />
      </Card>

      {data && (
        <>
          <Card
            title={
              <>
                Why <span className="mono">{data.user_id}</span> gets {data.result.assigned ? <span className="mono">{data.result.variant_key}</span> : 'no variant'}
              </>
            }
            actions={
              experimentId && (
                <Link to={`/experiments/${experimentId}`} className="mono small">
                  {data.experiment_key}
                </Link>
              )
            }
          >
            <ResultNotice result={data.result} />
            <ExplanationChecklist lines={data.explanation} />
            {Object.keys(data.context ?? {}).length > 0 && (
              <p className="muted small">
                Context used: <span className="mono">{JSON.stringify(data.context)}</span>
              </p>
            )}
          </Card>

          <div className="two-col">
            <Card title="Recorded assignment">
              {data.recorded_assignment ? (
                <div className="stack-sm">
                  <dl className="kv">
                    <dt>Variant</dt>
                    <dd className="mono">{data.recorded_assignment.variant_key}</dd>
                    <dt>Bucket</dt>
                    <dd className="mono">{data.recorded_assignment.bucket}</dd>
                    <dt>Version</dt>
                    <dd>v{data.recorded_assignment.version_number}</dd>
                    <dt>Assigned</dt>
                    <dd>{formatDateTime(data.recorded_assignment.assigned_at)}</dd>
                  </dl>
                  {data.recorded_assignment.config_at_assignment && (
                    <>
                      <h3 className="subhead">Config at assignment</h3>
                      <VersionConfigView config={data.recorded_assignment.config_at_assignment} highlight={data.recorded_assignment.variant_key} />
                    </>
                  )}
                  {data.recorded_assignment.variant_key !== data.result.variant_key && (
                    <div className="notice notice-warn">
                      A replay now gives {data.result.variant_key ? <span className="mono">{data.result.variant_key}</span> : 'no variant'}, which differs from the recorded
                      assignment. The config has changed since then; sticky assignment keeps users on their original variant.
                    </div>
                  )}
                </div>
              ) : (
                <Empty>No recorded assignment for this user.</Empty>
              )}
            </Card>
            <Card title="Sticky assignment">
              {data.sticky ? (
                <dl className="kv">
                  <dt>Variant</dt>
                  <dd className="mono">{data.sticky.variant_key}</dd>
                  <dt>Bucket</dt>
                  <dd className="mono">{data.sticky.bucket}</dd>
                  <dt>Version</dt>
                  <dd>v{data.sticky.version_number}</dd>
                  <dt>Since</dt>
                  <dd>{formatDateTime(data.sticky.assigned_at)}</dd>
                </dl>
              ) : (
                <Empty>No sticky assignment stored.</Empty>
              )}
            </Card>
          </div>
          <StepTrace steps={data.evaluation_steps} />
        </>
      )}
    </>
  );
}

function UserAssignments({
  initialUser,
  onUser,
  onExplain,
}: {
  initialUser: string;
  onUser: (userId: string) => void;
  onExplain: (experimentId: string, userId: string) => void;
}) {
  const [userId, setUserId] = useState(initialUser);
  const [data, setData] = useState<UserAssignmentsResponse | null>(null);
  const run = useAction(engine.userAssignments);

  async function submit(e: FormEvent) {
    e.preventDefault();
    const u = userId.trim();
    if (!u) return;
    onUser(u);
    setData((await run.run(u)) ?? null);
  }

  return (
    <Card>
      <form className="ask-form" onSubmit={submit}>
        <input aria-label="User ID" className="mono" placeholder="user_123" value={userId} onChange={(e) => setUserId(e.target.value)} />
        <button type="submit" className="btn btn-primary" disabled={run.busy || !userId.trim()}>
          {run.busy ? 'Loading…' : 'List assignments'}
        </button>
      </form>
      <ErrorBox error={run.error} feature="User assignments" />
      {data && data.assignments.length === 0 && <Empty>No recorded assignments for {data.user_id}.</Empty>}
      {data && data.assignments.length > 0 && (
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>Experiment</th>
                <th>Variant</th>
                <th className="num hide-sm">Bucket</th>
                <th className="hide-sm">Assigned</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {data.assignments.map((a) => (
                <tr key={`${a.experiment_id}-${a.assigned_at}`}>
                  <td>
                    <Link to={`/experiments/${a.experiment_id}`} className="mono">
                      {a.experiment_key}
                    </Link>
                    <div className="muted small">v{a.version_number}</div>
                  </td>
                  <td className="mono">{a.variant_key}</td>
                  <td className="num mono hide-sm">{a.bucket}</td>
                  <td className="small hide-sm">{formatDateTime(a.assigned_at)}</td>
                  <td>
                    <button type="button" className="btn btn-small" onClick={() => onExplain(a.experiment_id, data.user_id)}>
                      Explain
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Card>
  );
}

function ReplayByKey() {
  const projectList = useAsync(() => projects.list(), 'dbg-projects');
  const [key, setKey] = useState('');
  const [userId, setUserId] = useState('');
  const [projectId, setProjectId] = useState('');
  const [contextText, setContextText] = useState('{\n  "country": "US",\n  "platform": "ios"\n}');
  const [contextError, setContextError] = useState<string | null>(null);
  const [result, setResult] = useState<DebugResponse | null>(null);
  const debug = useAction(engine.debug);

  async function submit(e: FormEvent) {
    e.preventDefault();
    const ctx = parseContext(contextText);
    setContextError(ctx.error ?? null);
    if (ctx.error) return;
    const res = await debug.run(key.trim(), userId.trim(), ctx.value ?? {}, projectId || undefined);
    setResult(res ?? null);
  }

  return (
    <>
      <Card>
        <form onSubmit={submit}>
          <div className="form-grid">
            <Field label="Experiment key" htmlFor="dbg-key">
              <input id="dbg-key" className="mono" required value={key} placeholder="checkout_v3" onChange={(e) => setKey(e.target.value)} />
            </Field>
            <Field label="User ID" htmlFor="dbg-user">
              <input id="dbg-user" className="mono" required value={userId} placeholder="user_123" onChange={(e) => setUserId(e.target.value)} />
            </Field>
            <Field label="Project" htmlFor="dbg-project" hint="Needed only when the key exists in several projects.">
              <select id="dbg-project" value={projectId} onChange={(e) => setProjectId(e.target.value)}>
                <option value="">Any project</option>
                {projectList.data?.results.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name}
                  </option>
                ))}
              </select>
            </Field>
          </div>
          <Field label="Context (JSON)" htmlFor="dbg-ctx" hint={contextError ?? 'Attributes evaluated against targeting rules.'}>
            <textarea id="dbg-ctx" className={`mono ${contextError ? 'invalid' : ''}`} rows={5} value={contextText} onChange={(e) => setContextText(e.target.value)} />
          </Field>
          <div className="form-actions">
            <button type="submit" className="btn btn-primary" disabled={debug.busy || !key.trim() || !userId.trim()}>
              {debug.busy ? 'Evaluating…' : 'Evaluate'}
            </button>
          </div>
        </form>
        <ErrorBox error={debug.error} />
      </Card>

      {result && (
        <>
          <Card
            title="Result"
            actions={
              <Link to={`/experiments/${result.experiment.id}`} className="mono small">
                {result.experiment.key}
              </Link>
            }
          >
            <ResultNotice result={result.result} />
            <dl className="kv">
              <dt>Status</dt>
              <dd>
                <StatusBadge status={result.experiment.status} />
              </dd>
              <dt>Version</dt>
              <dd>{result.version ? `v${result.version.version_number} · allocation ${bpToPct(result.version.traffic_allocation)}` : 'none'}</dd>
              <dt>Reason</dt>
              <dd className="mono">{result.result.reason}</dd>
              {result.result.source && (
                <>
                  <dt>Source</dt>
                  <dd>{result.result.source}</dd>
                </>
              )}
              <dt>Config cache</dt>
              <dd>{result.cache_status}</dd>
              {result.result.variant_payload && Object.keys(result.result.variant_payload).length > 0 && (
                <>
                  <dt>Payload</dt>
                  <dd className="mono small">{JSON.stringify(result.result.variant_payload)}</dd>
                </>
              )}
            </dl>
          </Card>
          <StepTrace steps={result.evaluation_steps} />
        </>
      )}
    </>
  );
}

// ---------------------------------------------------------------------------

function ResultNotice({ result }: { result: EvaluationResult }) {
  return (
    <div className={`notice ${result.assigned ? 'notice-good' : 'notice-warn'}`}>
      {result.assigned ? (
        <span>
          ✓ Assigned to <strong className="mono">{result.variant_key}</strong> (bucket {result.bucket}, v{result.version_number})
        </span>
      ) : (
        <span>✗ Not assigned: {humanize(result.reason)}</span>
      )}
    </div>
  );
}

function ExplanationChecklist({ lines }: { lines: string[] }) {
  if (!lines.length) return null;
  return (
    <ul className="checks-list" aria-label="Explanation">
      {lines.map((line, i) => {
        const l = parseExplanationLine(line);
        return (
          <li key={i} className={l.status}>
            <span className="check-mark" aria-label={l.status === 'pass' ? 'passed' : l.status === 'fail' ? 'failed' : 'info'}>
              {l.status === 'pass' ? '✓' : l.status === 'fail' ? '✗' : '•'}
            </span>
            <span>{l.text}</span>
          </li>
        );
      })}
    </ul>
  );
}

function StepTrace({ steps }: { steps: DebugStep[] }) {
  return (
    <Card title="Evaluation trace">
      <ol className="trace">
        {steps.map((s, i) => {
          const status = s.passed === true ? 'pass' : s.passed === false ? 'fail' : 'skip';
          return (
            <li key={i} className={status}>
              <span className="check-mark" aria-label={status === 'pass' ? 'passed' : status === 'fail' ? 'failed' : 'info'}>
                {status === 'pass' ? '✓' : status === 'fail' ? '✗' : '•'}
              </span>
              <div>
                <div>
                  <strong>{humanize(s.step)}</strong>{' '}
                  <Badge tone={status === 'pass' ? 'good' : status === 'fail' ? 'bad' : 'neutral'}>{status === 'skip' ? 'info' : status}</Badge>
                </div>
                <div className="muted small">{s.detail}</div>
              </div>
            </li>
          );
        })}
      </ol>
    </Card>
  );
}
