import { experiments, type Experiment } from '../../api';
import { Badge, Card, Empty, ErrorBox, Loading } from '../../components/ui';
import { formatNumber, formatSignedPct, humanize, type Tone } from '../../lib/format';
import { useAsync } from '../../lib/useAsync';

const STATUS_TONE: Record<string, Tone> = { healthy: 'good', warning: 'warn', critical: 'bad' };

export function ProductionTab({ experiment }: { experiment: Experiment }) {
  const impact = useAsync(() => experiments.productionImpact(experiment.id), `impact-${experiment.id}`);
  const anomalies = useAsync(() => experiments.anomalies(experiment.id), `anom-${experiment.id}`);
  const data = impact.data;
  const variantEntries = Object.entries(data?.impact ?? {});

  return (
    <div className="stack">
      <Card title="Production impact vs control">
        {impact.loading && <Loading />}
        <ErrorBox error={impact.error} onRetry={impact.reload} />
        {data && variantEntries.length === 0 && <Empty>{data.message ?? 'No telemetry data available.'}</Empty>}
        {variantEntries.map(([variant, metrics]) => (
          <div key={variant} className="stack-sm">
            <h3 className="subhead">
              <span className="mono">{variant}</span>
            </h3>
            <div className="table-wrap">
              <table className="table">
                <thead>
                  <tr>
                    <th>Metric</th>
                    <th className="num">Control</th>
                    <th className="num">Variant</th>
                    <th className="num">Change</th>
                    <th>Status</th>
                  </tr>
                </thead>
                <tbody>
                  {Object.entries(metrics).map(([metric, m]) => (
                    <tr key={metric}>
                      <td className="mono">{metric}</td>
                      <td className="num">{formatNumber(m.control_avg, 2)}</td>
                      <td className="num">{formatNumber(m.variant_avg, 2)}</td>
                      <td className="num">{formatSignedPct(m.change_pct)}</td>
                      <td>
                        <Badge tone={STATUS_TONE[m.status] ?? 'neutral'}>
                          {m.status === 'healthy' ? '✓' : '⚠'} {m.status}
                        </Badge>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        ))}
      </Card>

      <Card title="Anomalies">
        {anomalies.loading && <Loading />}
        <ErrorBox error={anomalies.error} onRetry={anomalies.reload} />
        {anomalies.data &&
          (anomalies.data.anomalies.length === 0 ? (
            <div className="notice notice-good">✓ No harmful anomalies detected in treatment telemetry.</div>
          ) : (
            <ul className="alert-list">
              {anomalies.data.anomalies.map((a, i) => (
                <li key={i} className="alert-item tone-bad">
                  <div>
                    <strong className="mono">{a.metric_name}</strong> on <span className="mono">{a.variant_key}</span>
                  </div>
                  <div className="muted small">
                    {Object.entries(a)
                      .filter(([k, v]) => !['metric_name', 'variant_key'].includes(k) && (typeof v === 'number' || typeof v === 'string'))
                      .map(([k, v]) => `${humanize(k)}: ${typeof v === 'number' ? formatNumber(v, 3) : v}`)
                      .join(' · ')}
                  </div>
                </li>
              ))}
            </ul>
          ))}
      </Card>
    </div>
  );
}
