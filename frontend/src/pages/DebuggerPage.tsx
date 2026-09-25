import { useState, type FormEvent } from 'react';
import { Link } from 'react-router-dom';
import { engine, type DebugResponse } from '../api';
import { Badge, Card, ErrorBox, Field, StatusBadge } from '../components/ui';
import { bpToPct, humanize } from '../lib/format';
import { useAction } from '../lib/useAsync';

export function DebuggerPage() {
  const [key, setKey] = useState('');
  const [userId, setUserId] = useState('');
  const [contextText, setContextText] = useState('{\n  "country": "US",\n  "platform": "ios"\n}');
  const [contextError, setContextError] = useState<string | null>(null);
  const [result, setResult] = useState<DebugResponse | null>(null);
  const debug = useAction(engine.debug);

  async function submit(e: FormEvent) {
    e.preventDefault();
    let context: Record<string, unknown> = {};
    if (contextText.trim()) {
      try {
        const parsed: unknown = JSON.parse(contextText);
        if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) throw new Error('Context must be a JSON object.');
        context = parsed as Record<string, unknown>;
      } catch (err) {
        setContextError(err instanceof Error ? err.message : 'Invalid JSON.');
        return;
      }
    }
    setContextError(null);
    const res = await debug.run(key.trim(), userId.trim(), context);
    setResult(res ?? null);
  }

  return (
    <div className="page">
      <div className="page-header">
        <h1>Assignment Debugger</h1>
      </div>
      <Card>
        <form onSubmit={submit}>
          <div className="form-grid">
            <Field label="Experiment key" htmlFor="dbg-key">
              <input id="dbg-key" className="mono" required value={key} placeholder="checkout_v3" onChange={(e) => setKey(e.target.value)} />
            </Field>
            <Field label="User ID" htmlFor="dbg-user">
              <input id="dbg-user" className="mono" required value={userId} placeholder="user_123" onChange={(e) => setUserId(e.target.value)} />
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
            <div className={`notice ${result.result.assigned ? 'notice-good' : 'notice-warn'}`}>
              {result.result.assigned ? (
                <>
                  ✓ Assigned to <strong className="mono">{result.result.variant_key}</strong> (bucket {result.result.bucket}, v{result.result.version_number})
                </>
              ) : (
                <>✗ Not assigned — {humanize(result.result.reason)}</>
              )}
            </div>
            <dl className="kv">
              <dt>Status</dt>
              <dd>
                <StatusBadge status={result.experiment.status} />
              </dd>
              <dt>Version</dt>
              <dd>
                {result.version ? `v${result.version.version_number} · allocation ${bpToPct(result.version.traffic_allocation)}` : 'none'}
              </dd>
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
          <Card title="Evaluation trace">
            <ol className="trace">
              {result.evaluation_steps.map((s, i) => (
                <li key={i} className={s.passed === true ? 'pass' : s.passed === false ? 'fail' : 'skip'}>
                  <span className="check-mark" aria-label={s.passed === true ? 'passed' : s.passed === false ? 'failed' : 'info'}>
                    {s.passed === true ? '✓' : s.passed === false ? '✗' : '•'}
                  </span>
                  <div>
                    <div>
                      <strong>{humanize(s.step)}</strong> <Badge tone={s.passed === true ? 'good' : s.passed === false ? 'bad' : 'neutral'}>{s.passed === true ? 'pass' : s.passed === false ? 'fail' : 'info'}</Badge>
                    </div>
                    <div className="muted small">{s.detail}</div>
                  </div>
                </li>
              ))}
            </ol>
          </Card>
        </>
      )}
    </div>
  );
}
