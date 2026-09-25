import { useState, type FormEvent } from 'react';
import { experiments, type Experiment, type ExperimentSnapshot } from '../api';
import { bpToPct, formatDateTime, localInputToIso, nowLocalInput } from '../lib/format';
import { useAction } from '../lib/useAsync';
import { Card, ErrorBox, StatusBadge } from './ui';
import { VersionConfigView } from './VersionConfigView';

/** "What did this experiment look like at …?" via GET /experiments/{id}/history/?at=. */
export function TimeTravel({ experiment }: { experiment: Experiment }) {
  const [value, setValue] = useState(nowLocalInput);
  const [snapshot, setSnapshot] = useState<ExperimentSnapshot | null>(null);
  const load = useAction(experiments.history);

  async function submit(e: FormEvent) {
    e.preventDefault();
    const iso = localInputToIso(value);
    if (!iso) return;
    const res = await load.run(experiment.id, iso);
    setSnapshot(res ?? null);
  }

  return (
    <Card title="Time travel">
      <form className="time-travel-form" onSubmit={submit}>
        <label htmlFor="tt-at" className="muted small">
          State at
        </label>
        <input id="tt-at" type="datetime-local" value={value} max={nowLocalInput()} onChange={(e) => setValue(e.target.value)} required />
        <button type="submit" className="btn" disabled={load.busy || !localInputToIso(value)}>
          {load.busy ? 'Loading…' : 'Show'}
        </button>
      </form>
      <ErrorBox error={load.error} feature="Time travel" />
      {snapshot && (
        <div className="stack-sm time-travel-result">
          <div className="decision-head">
            <span className="muted small">{formatDateTime(snapshot.at)}</span>
            <StatusBadge status={snapshot.status} />
            <span>
              Rollout <strong>{bpToPct(snapshot.rollout_percentage)}</strong>
            </span>
          </div>
          {snapshot.version ? <VersionConfigView config={snapshot.version} /> : <p className="muted">No version existed at that time.</p>}
        </div>
      )}
    </Card>
  );
}
