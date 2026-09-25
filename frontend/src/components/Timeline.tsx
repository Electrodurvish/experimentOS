import type { TimelineEvent } from '../api';
import { formatDay, formatTime, humanize, type Tone } from '../lib/format';

const EVENT_TONES: Record<string, Tone> = {
  experiment_started: 'good',
  experiment_resumed: 'good',
  experiment_paused: 'warn',
  experiment_completed: 'info',
  rollout_changed: 'info',
  guardrail_breached: 'bad',
  rollback_triggered: 'bad',
  anomaly_detected: 'bad',
  srm_detected: 'warn',
  paradox_detected: 'warn',
  interaction_detected: 'warn',
  decision_made: 'info',
};

function eventTone(type: string): Tone {
  return EVENT_TONES[type] ?? 'neutral';
}

/** Vertical chronological timeline, grouped by day (oldest first, as in the plan). */
export function Timeline({ events }: { events: TimelineEvent[] }) {
  if (!events.length) return <p className="muted">No timeline events yet.</p>;
  const sorted = [...events].sort((a, b) => a.created_at.localeCompare(b.created_at));
  const groups: { day: string; items: TimelineEvent[] }[] = [];
  for (const e of sorted) {
    const day = formatDay(e.created_at);
    const last = groups[groups.length - 1];
    if (last && last.day === day) last.items.push(e);
    else groups.push({ day, items: [e] });
  }
  return (
    <div className="timeline">
      {groups.map((g) => (
        <section key={g.day}>
          <h3 className="timeline-day">{g.day}</h3>
          <ol className="timeline-list">
            {g.items.map((e, i) => (
              <li key={e.id ?? `${e.created_at}-${i}`} className={`timeline-item tone-${eventTone(e.event_type)}`}>
                <time dateTime={e.created_at} className="timeline-time">
                  {formatTime(e.created_at)}
                </time>
                <div className="timeline-content">
                  <div className="timeline-title">{e.title || humanize(e.event_type)}</div>
                  {e.detail && <div className="timeline-detail">{e.detail}</div>}
                  <div className="timeline-type">{humanize(e.event_type)}</div>
                </div>
              </li>
            ))}
          </ol>
        </section>
      ))}
    </div>
  );
}
