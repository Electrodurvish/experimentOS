import { bpToPct } from '../lib/format';

export function RolloutBar({ bp, label = true }: { bp: number; label?: boolean }) {
  const pct = Math.max(0, Math.min(100, bp / 100));
  return (
    <div className="rollout-bar-wrap">
      <div
        className="rollout-bar"
        role="meter"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={pct}
        aria-label="Rollout"
      >
        <div className="rollout-bar-fill" style={{ width: `${pct}%` }} />
      </div>
      {label && <span className="rollout-bar-label">{bpToPct(bp)}</span>}
    </div>
  );
}
