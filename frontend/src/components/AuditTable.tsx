import type { AuditLog } from '../api';
import { formatDateTime, humanize } from '../lib/format';

function brief(value: unknown): string {
  if (value === null || value === undefined) return '';
  if (typeof value === 'object' && !Array.isArray(value) && Object.keys(value as object).length === 0) return '';
  const s = typeof value === 'string' ? value : JSON.stringify(value);
  return s.length > 160 ? `${s.slice(0, 157)}…` : s;
}

export function AuditTable({ logs, experimentKeys }: { logs: AuditLog[]; experimentKeys?: Record<string, string> }) {
  return (
    <ul className="audit-list">
      {logs.map((l) => {
        const oldV = brief(l.old_value);
        const newV = brief(l.new_value);
        return (
          <li key={l.id}>
            <div className="audit-head">
              <strong>{humanize(l.action)}</strong>
              {l.experiment && experimentKeys?.[l.experiment] && <span className="mono small">{experimentKeys[l.experiment]}</span>}
              <span className="muted small">
                {formatDateTime(l.created_at)} · {l.actor_email ?? 'system'}
              </span>
            </div>
            {(oldV || newV) && (
              <div className="audit-diff mono small">
                {oldV && <span className="neg">− {oldV}</span>}
                {newV && <span className="pos">+ {newV}</span>}
              </div>
            )}
          </li>
        );
      })}
    </ul>
  );
}
