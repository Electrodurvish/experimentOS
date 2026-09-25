import { useState } from 'react';
import { interactions, type InteractionPairInput, type InteractionsResponse } from '../api';
import { Badge, Card, ErrorBox } from '../components/ui';
import { formatPValue, formatRate } from '../lib/format';
import { useAction } from '../lib/useAsync';

const SAMPLE = `[
  {
    "experiment_a": "checkout_v3",
    "experiment_b": "pricing_banner",
    "a_only":  {"users": 5000, "conversions": 600},
    "b_only":  {"users": 5000, "conversions": 550},
    "both":    {"users": 5000, "conversions": 450},
    "neither": {"users": 5000, "conversions": 500}
  }
]`;

export function InteractionsPage() {
  const [text, setText] = useState(SAMPLE);
  const [parseError, setParseError] = useState<string | null>(null);
  const [data, setData] = useState<InteractionsResponse | null>(null);
  const detect = useAction(interactions.detect);

  async function run() {
    let pairs: InteractionPairInput[];
    try {
      const parsed: unknown = JSON.parse(text);
      if (!Array.isArray(parsed)) throw new Error('Expected a JSON array of pairs.');
      pairs = parsed as InteractionPairInput[];
    } catch (e) {
      setParseError(e instanceof Error ? e.message : 'Invalid JSON');
      return;
    }
    setParseError(null);
    const res = await detect.run(pairs);
    if (res) setData(res);
  }

  return (
    <div className="page">
      <div className="page-header">
        <h1>Experiment Interactions</h1>
      </div>
      <Card title="Overlap data">
        <p className="muted small">
          For each pair of concurrent experiments, provide users and conversions in A only, B only, both, and neither. The backend flags
          non-additive (synergistic or antagonistic) effects.
        </p>
        <textarea className="mono" rows={12} aria-label="Pairs JSON" value={text} onChange={(e) => setText(e.target.value)} />
        {parseError && <div className="notice notice-error">{parseError}</div>}
        <ErrorBox error={detect.error} />
        <div className="form-actions">
          <button type="button" className="btn btn-primary" onClick={run} disabled={detect.busy}>
            Detect interactions
          </button>
        </div>
      </Card>
      {data && (
        <Card title="Results">
          <ul className="history-list">
            {data.interactions.map((r, i) => (
              <li key={i}>
                <div>
                  <span className="mono">{r.experiment_a}</span> × <span className="mono">{r.experiment_b}</span>{' '}
                  <Badge tone={r.is_interaction ? (r.interaction_type === 'antagonistic' ? 'bad' : 'good') : 'neutral'}>
                    {r.is_interaction ? r.interaction_type : 'no interaction'}
                  </Badge>
                </div>
                <div className="muted small">
                  expected combined {formatRate(r.expected_combined_rate, 2)} · actual {formatRate(r.actual_combined_rate, 2)} · effect{' '}
                  {formatRate(r.interaction_effect, 2)}
                  {typeof r.combined_p_value === 'number' ? ` · p ${formatPValue(r.combined_p_value)}` : ''}
                </div>
              </li>
            ))}
          </ul>
          {data.graph.edges.length > 0 && (
            <>
              <h3 className="subhead">Interaction graph</h3>
              <ul className="plain-list">
                {data.graph.edges.map((e, i) => (
                  <li key={i}>
                    <span className="mono">{e.from}</span> ↔ <span className="mono">{e.to}</span> — {e.type} ({formatRate(e.effect, 2)})
                  </li>
                ))}
              </ul>
            </>
          )}
        </Card>
      )}
    </div>
  );
}
