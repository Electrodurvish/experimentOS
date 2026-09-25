import type { DecisionCheck, Evidence } from '../api';
import { humanize } from '../lib/format';

/** Numbered evidence list (E1, E2, …). Highlights ids in `cited`. */
export function EvidenceList({ evidence, cited }: { evidence: Evidence[]; cited?: string[] }) {
  if (!evidence.length) return <p className="muted">No evidence recorded.</p>;
  const citedSet = new Set(cited ?? []);
  return (
    <ol className="evidence-list">
      {evidence.map((e, i) => (
        <li key={e.id || i} id={`evidence-${e.id}`} className={citedSet.has(e.id) ? 'cited' : undefined}>
          <span className="evidence-id">{e.id || `E${i + 1}`}</span>
          <span className="evidence-body">
            {e.statement}
            {e.kind && <span className="evidence-kind">{humanize(e.kind)}</span>}
          </span>
        </li>
      ))}
    </ol>
  );
}

/** Checks shown as ✓ / ✗ with their detail. */
export function ChecksList({ checks }: { checks: DecisionCheck[] }) {
  if (!checks.length) return <p className="muted">No checks evaluated.</p>;
  return (
    <ul className="checks-list">
      {checks.map((c) => (
        <li key={c.name} className={c.passed ? 'pass' : 'fail'}>
          <span className="check-mark" aria-label={c.passed ? 'passed' : 'failed'}>
            {c.passed ? '✓' : '✗'}
          </span>
          <span>
            <strong>{c.label || humanize(c.name)}</strong>
            {c.detail && <span className="muted"> — {c.detail}</span>}
          </span>
        </li>
      ))}
    </ul>
  );
}
