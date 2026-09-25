import { useState } from 'react';
import { experiments, type Experiment, type SegmentAnalysis, type SegmentInput } from '../../api';
import { Badge, Card, ErrorBox } from '../../components/ui';
import { formatLift, formatNumber, formatPValue, formatRate } from '../../lib/format';
import { emptyRow, parseSegmentJson, rowsToSegments, segmentsToRows, type SegmentRow } from '../../lib/segments';
import { useAction } from '../../lib/useAsync';

const SAMPLE = `[
  {"dimension": "platform", "value": "ios", "control": {"users": 5000, "conversions": 500}, "treatment": {"users": 5000, "conversions": 600}},
  {"dimension": "platform", "value": "android", "control": {"users": 4000, "conversions": 420}, "treatment": {"users": 4000, "conversions": 380}}
]`;

const COLUMNS: { field: keyof SegmentRow; label: string; numeric?: boolean }[] = [
  { field: 'dimension', label: 'Dimension' },
  { field: 'value', label: 'Value' },
  { field: 'controlUsers', label: 'Control users', numeric: true },
  { field: 'controlConversions', label: 'Control conv.', numeric: true },
  { field: 'treatmentUsers', label: 'Treatment users', numeric: true },
  { field: 'treatmentConversions', label: 'Treatment conv.', numeric: true },
];

export function SegmentsTab({ experiment }: { experiment: Experiment }) {
  const [mode, setMode] = useState<'table' | 'json'>('table');
  const [rows, setRows] = useState<SegmentRow[]>([emptyRow(), emptyRow()]);
  const [json, setJson] = useState(SAMPLE);
  const [aggregate, setAggregate] = useState('');
  const [inputErrors, setInputErrors] = useState<string[]>([]);
  const [analysis, setAnalysis] = useState<SegmentAnalysis | null>(null);
  const run = useAction(experiments.segments);

  function switchMode(next: 'table' | 'json') {
    if (next === mode) return;
    if (next === 'json') {
      const { segments } = rowsToSegments(rows);
      if (segments.length) setJson(JSON.stringify(segments, null, 2));
    } else {
      const parsed = parseSegmentJson(json);
      if (!parsed.errors.length && parsed.segments.length) setRows(segmentsToRows(parsed.segments));
    }
    setMode(next);
  }

  async function analyze() {
    let segments: SegmentInput[];
    let aggregateLift: number | undefined;
    let errors: string[];
    if (mode === 'table') {
      ({ segments, errors } = rowsToSegments(rows));
    } else {
      ({ segments, aggregateLift, errors } = parseSegmentJson(json));
    }
    if (aggregate.trim()) {
      const n = Number(aggregate);
      if (Number.isFinite(n)) aggregateLift = n / 100;
      else errors = [...errors, 'Aggregate lift must be a number (percent).'];
    }
    setInputErrors(errors);
    if (errors.length) return;
    const res = await run.run(experiment.id, segments, aggregateLift);
    if (res) setAnalysis(res.analysis);
  }

  return (
    <div className="stack">
      <Card
        title="Segment Explorer"
        actions={
          <div className="segmented" role="tablist">
            <button type="button" role="tab" aria-selected={mode === 'table'} className={mode === 'table' ? 'active' : ''} onClick={() => switchMode('table')}>
              Table
            </button>
            <button type="button" role="tab" aria-selected={mode === 'json'} className={mode === 'json' ? 'active' : ''} onClick={() => switchMode('json')}>
              JSON
            </button>
          </div>
        }
      >
        <p className="muted small">
          Enter per-segment control and treatment counts. The backend computes lift, significance, each segment’s contribution to the
          overall effect, and flags Simpson’s paradox (segments moving opposite to the aggregate).
        </p>
        {mode === 'table' ? (
          <div className="segment-rows">
            {rows.map((r, i) => (
              <div key={i} className="segment-row">
                {COLUMNS.map((c) => (
                  <input
                    key={c.field}
                    aria-label={`Row ${i + 1} ${c.label}`}
                    placeholder={c.label}
                    inputMode={c.numeric ? 'numeric' : undefined}
                    value={r[c.field]}
                    onChange={(e) => setRows((rs) => rs.map((x, j) => (j === i ? { ...x, [c.field]: e.target.value } : x)))}
                  />
                ))}
                <button
                  type="button"
                  className="btn btn-small btn-danger-ghost"
                  aria-label={`Remove row ${i + 1}`}
                  onClick={() => setRows((rs) => (rs.length > 1 ? rs.filter((_, j) => j !== i) : [emptyRow()]))}
                >
                  ✕
                </button>
              </div>
            ))}
            <button type="button" className="btn btn-small" onClick={() => setRows((rs) => [...rs, emptyRow()])}>
              + Add row
            </button>
          </div>
        ) : (
          <textarea className="mono" rows={10} aria-label="Segments JSON" value={json} onChange={(e) => setJson(e.target.value)} />
        )}
        <div className="form-grid">
          <div className="field">
            <label htmlFor="agg">Aggregate lift (%, optional)</label>
            <input id="agg" inputMode="decimal" placeholder="auto from results" value={aggregate} onChange={(e) => setAggregate(e.target.value)} />
          </div>
          <div className="button-row">
            <button type="button" className="btn btn-primary" onClick={analyze} disabled={run.busy}>
              {run.busy ? 'Analyzing…' : 'Analyze segments'}
            </button>
          </div>
        </div>
        {inputErrors.length > 0 && (
          <div className="notice notice-error" role="alert">
            <ul>
              {inputErrors.map((e) => (
                <li key={e}>{e}</li>
              ))}
            </ul>
          </div>
        )}
        <ErrorBox error={run.error} />
      </Card>

      {analysis && (
        <Card title="Segment analysis">
          {analysis.paradox_detected ? (
            <div className="notice notice-warn">
              <strong>Simpson’s paradox detected</strong> in {analysis.paradox_segments.length} segment(s):{' '}
              {analysis.paradox_segments.map((p) => `${p.dimension}=${p.value} (${formatLift(p.segment_lift)} vs ${formatLift(p.aggregate_lift)} overall)`).join('; ')}
            </div>
          ) : (
            <div className="notice notice-good">✓ No segment moves against the aggregate effect.</div>
          )}
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th>Segment</th>
                  <th className="num hide-sm">Control</th>
                  <th className="num hide-sm">Treatment</th>
                  <th className="num">Lift</th>
                  <th className="num">p-value</th>
                  <th className="num">Contribution</th>
                </tr>
              </thead>
              <tbody>
                {analysis.segments.map((s) => (
                  <tr key={`${s.dimension}=${s.value}`} className={s.has_paradox ? 'row-warn' : undefined}>
                    <td>
                      <span className="mono">
                        {s.dimension}={s.value}
                      </span>{' '}
                      {s.has_paradox && <Badge tone="warn">paradox</Badge>}
                    </td>
                    <td className="num hide-sm">
                      {formatRate(s.control_rate, 2)}
                      <div className="muted small">{formatNumber(s.control_users)} users</div>
                    </td>
                    <td className="num hide-sm">
                      {formatRate(s.treatment_rate, 2)}
                      <div className="muted small">{formatNumber(s.treatment_users)} users</div>
                    </td>
                    <td className={`num ${s.lift >= 0 ? 'pos' : 'neg'}`}>{formatLift(s.lift)}</td>
                    <td className="num">
                      {formatPValue(s.p_value)} <Badge tone={s.is_significant ? 'good' : 'neutral'}>{s.is_significant ? 'sig.' : 'n.s.'}</Badge>
                    </td>
                    <td className="num">
                      <div className="contrib">
                        <div className="contrib-bar" style={{ width: `${Math.min(100, s.contribution_pct)}%` }} />
                        <span>{s.contribution_pct.toFixed(1)}%</span>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}
    </div>
  );
}
