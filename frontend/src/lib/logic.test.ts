import type { Decision, Experiment, ExperimentResults, TimelineEvent } from '../api';
import { collectAlerts, sortAlerts } from './alerts';
import { splitArms } from './results';
import { canMutate } from './roles';
import { parseStages } from './rollout';
import { parseSegmentJson, rowsToSegments } from './segments';

describe('splitArms', () => {
  const results: ExperimentResults = {
    experiment_id: 'e1',
    experiment_key: 'checkout_v3',
    srm: null,
    recommended_sample_size_per_variant: 0,
    variants: {
      control: { exposures: 1, unique_users: 1000, conversions: 101, conversion_rate: 0.101, ci_lower: 0.08, ci_upper: 0.12 },
      treatment: {
        exposures: 1,
        unique_users: 1000,
        conversions: 124,
        conversion_rate: 0.124,
        ci_lower: 0.1,
        ci_upper: 0.14,
        lift: 0.228,
        p_value: 0.01,
        is_significant: true,
      },
    },
  };

  it('uses the arm without lift as control', () => {
    const arms = splitArms(results);
    expect(arms.control?.key).toBe('control');
    expect(arms.treatment?.key).toBe('treatment');
  });

  it('prefers the configured control variant', () => {
    const exp = { current_version: { variants: [{ key: 'treatment', is_control: true }] } } as unknown as Experiment;
    expect(splitArms(results, exp).control?.key).toBe('treatment');
  });

  it('handles empty results', () => {
    expect(splitArms(undefined)).toEqual({ control: null, treatment: null, treatments: [] });
  });
});

describe('canMutate', () => {
  it('allows everything when memberships are absent', () => {
    expect(canMutate({ id: '1', email: 'a@b.c' })).toBe(true);
  });
  it('blocks analysts and viewers', () => {
    const user = { id: '1', email: 'a', memberships: [{ organization_id: 'o', organization_name: 'O', role: 'ANALYST' as const }] };
    expect(canMutate(user)).toBe(false);
    expect(canMutate({ ...user, memberships: [{ ...user.memberships[0]!, role: 'EXPERIMENT_MANAGER' as const }] })).toBe(true);
  });
  it('uses the org-specific role when given', () => {
    const user = {
      id: '1',
      email: 'a',
      memberships: [
        { organization_id: 'o1', organization_name: 'O1', role: 'VIEWER' as const },
        { organization_id: 'o2', organization_name: 'O2', role: 'ADMIN' as const },
      ],
    };
    expect(canMutate(user, 'o1')).toBe(false);
    expect(canMutate(user, 'o2')).toBe(true);
  });
});

describe('parseStages', () => {
  it('parses percent stages into basis points', () => {
    expect(parseStages('10, 25, 50, 100')).toEqual({ stages: [1000, 2500, 5000, 10000], error: null });
  });
  it('rejects non-ascending or invalid stages', () => {
    expect(parseStages('50, 25').error).toMatch(/ascending/);
    expect(parseStages('0, 10').error).toMatch(/not a percentage/);
    expect(parseStages('').error).toBeTruthy();
  });
});

describe('segments', () => {
  it('converts table rows, skipping blank ones', () => {
    const { segments, errors } = rowsToSegments([
      { dimension: 'country', value: 'IN', controlUsers: '100', controlConversions: '10', treatmentUsers: '100', treatmentConversions: '12' },
      { dimension: '', value: '', controlUsers: '', controlConversions: '', treatmentUsers: '', treatmentConversions: '' },
    ]);
    expect(errors).toEqual([]);
    expect(segments).toEqual([{ dimension: 'country', value: 'IN', control: { users: 100, conversions: 10 }, treatment: { users: 100, conversions: 12 } }]);
  });

  it('flags impossible counts', () => {
    const { errors } = rowsToSegments([
      { dimension: 'd', value: 'v', controlUsers: '10', controlConversions: '20', treatmentUsers: 'x', treatmentConversions: '1' },
    ]);
    expect(errors.some((e) => e.includes('treatment users'))).toBe(true);
    expect(errors.some((e) => e.includes('control conversions exceed users'))).toBe(true);
  });

  it('parses JSON in both accepted shapes', () => {
    const seg = { dimension: 'p', value: 'ios', control: { users: 1, conversions: 0 }, treatment: { users: 1, conversions: 1 } };
    expect(parseSegmentJson(JSON.stringify([seg])).segments).toHaveLength(1);
    const wrapped = parseSegmentJson(JSON.stringify({ segments: [seg], aggregate_lift: 0.1 }));
    expect(wrapped.aggregateLift).toBe(0.1);
    expect(parseSegmentJson('{oops').errors[0]).toMatch(/Invalid JSON/);
  });
});

describe('alerts', () => {
  it('keeps only alerting decisions and events, newest first', () => {
    const decisions = [
      { id: 'd1', recommendation: 'ROLLBACK', summary: 'Error rate breached', created_at: '2026-09-01T10:00:00Z' },
      { id: 'd2', recommendation: 'CONTINUE', summary: 'fine', created_at: '2026-09-01T11:00:00Z' },
      { id: 'd3', recommendation: 'DECREASE_ROLLOUT', summary: 'slow', created_at: '2026-09-01T12:00:00Z' },
    ] as Decision[];
    const timeline: TimelineEvent[] = [
      { event_type: 'rollout_changed', title: '25%', detail: '', metadata: {}, created_at: '2026-09-01T09:00:00Z' },
      { event_type: 'anomaly_detected', title: 'Latency anomaly', detail: 'android', metadata: {}, created_at: '2026-09-01T13:00:00Z' },
    ];
    const items = sortAlerts(collectAlerts('e1', 'checkout_v3', decisions, timeline));
    expect(items.map((i) => i.title)).toEqual(['Latency anomaly', 'Decision: DECREASE ROLLOUT', 'Decision: ROLLBACK']);
    expect(items.find((i) => i.title === 'Decision: ROLLBACK')?.severity).toBe('critical');
  });
});
