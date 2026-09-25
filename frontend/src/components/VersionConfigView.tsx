import type { VersionConfig } from '../api';
import { bpToPct, formatDateTime } from '../lib/format';
import { Badge } from './ui';

/** Read-only view of a version snapshot (config at assignment / time travel). */
export function VersionConfigView({ config, highlight }: { config: VersionConfig; highlight?: string }) {
  const hasTargeting = config.targeting !== null && config.targeting !== undefined && JSON.stringify(config.targeting) !== '{}';
  return (
    <div className="stack-sm">
      <div className="muted small">
        v{config.version_number} · allocation {bpToPct(config.traffic_allocation)} · created {formatDateTime(config.created_at)}
      </div>
      <div className="table-wrap">
        <table className="table">
          <thead>
            <tr>
              <th>Variant</th>
              <th className="num">Share</th>
              <th className="num">Buckets</th>
            </tr>
          </thead>
          <tbody>
            {[...config.variants]
              .sort((a, b) => a.bucket_start - b.bucket_start)
              .map((v) => (
                <tr key={v.key} className={v.key === highlight ? 'row-highlight' : undefined}>
                  <td>
                    <span className="mono">{v.key}</span> {v.is_control && <Badge>control</Badge>}{' '}
                    {v.key === highlight && <Badge tone="info">assigned</Badge>}
                  </td>
                  <td className="num">{bpToPct(v.traffic_percentage)}</td>
                  <td className="num mono">
                    {v.bucket_start}–{v.bucket_end}
                  </td>
                </tr>
              ))}
          </tbody>
        </table>
      </div>
      {hasTargeting && (
        <details className="details">
          <summary>Targeting rules</summary>
          <pre className="code-block">{JSON.stringify(config.targeting, null, 2)}</pre>
        </details>
      )}
    </div>
  );
}
