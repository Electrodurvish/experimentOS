import type { Decision, TimelineEvent } from '../api/types';

export const ALERT_RECOMMENDATIONS = new Set(['PAUSE', 'ROLLBACK', 'DECREASE_ROLLOUT']);
export const ALERT_EVENT_TYPES = new Set(['rollback_triggered', 'guardrail_breached', 'anomaly_detected']);

export interface AlertItem {
  id: string;
  experimentId: string;
  experimentKey: string;
  kind: 'decision' | 'event';
  severity: 'critical' | 'warning';
  title: string;
  detail: string;
  createdAt: string;
}

export function collectAlerts(
  experimentId: string,
  experimentKey: string,
  decisions: Decision[],
  timeline: TimelineEvent[],
): AlertItem[] {
  const items: AlertItem[] = [];
  for (const d of decisions) {
    if (!ALERT_RECOMMENDATIONS.has(d.recommendation)) continue;
    items.push({
      id: `d-${d.id}`,
      experimentId,
      experimentKey,
      kind: 'decision',
      severity: d.recommendation === 'DECREASE_ROLLOUT' ? 'warning' : 'critical',
      title: `Decision: ${d.recommendation.replace(/_/g, ' ')}`,
      detail: d.summary,
      createdAt: d.created_at,
    });
  }
  timeline.forEach((e, i) => {
    if (!ALERT_EVENT_TYPES.has(e.event_type)) return;
    items.push({
      id: `e-${e.id ?? `${experimentId}-${i}`}`,
      experimentId,
      experimentKey,
      kind: 'event',
      severity: e.event_type === 'anomaly_detected' ? 'warning' : 'critical',
      title: e.title,
      detail: e.detail,
      createdAt: e.created_at,
    });
  });
  return items;
}

export function sortAlerts(items: AlertItem[]): AlertItem[] {
  return [...items].sort((a, b) => b.createdAt.localeCompare(a.createdAt));
}
