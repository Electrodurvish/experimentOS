import type { SegmentInput } from '../api/types';

export interface SegmentRow {
  dimension: string;
  value: string;
  controlUsers: string;
  controlConversions: string;
  treatmentUsers: string;
  treatmentConversions: string;
}

export const emptyRow = (): SegmentRow => ({
  dimension: '',
  value: '',
  controlUsers: '',
  controlConversions: '',
  treatmentUsers: '',
  treatmentConversions: '',
});

function toCount(label: string, raw: unknown, errors: string[]): number {
  const n = typeof raw === 'number' ? raw : Number(String(raw ?? '').trim());
  if (!Number.isInteger(n) || n < 0) {
    errors.push(`${label} must be a non-negative integer.`);
    return 0;
  }
  return n;
}

export function rowsToSegments(rows: SegmentRow[]): { segments: SegmentInput[]; errors: string[] } {
  const errors: string[] = [];
  const segments: SegmentInput[] = [];
  rows.forEach((r, i) => {
    const blank = Object.values(r).every((v) => String(v).trim() === '');
    if (blank) return;
    const at = `Row ${i + 1}`;
    if (!r.dimension.trim() || !r.value.trim()) errors.push(`${at}: dimension and value are required.`);
    const seg: SegmentInput = {
      dimension: r.dimension.trim(),
      value: r.value.trim(),
      control: {
        users: toCount(`${at} control users`, r.controlUsers, errors),
        conversions: toCount(`${at} control conversions`, r.controlConversions, errors),
      },
      treatment: {
        users: toCount(`${at} treatment users`, r.treatmentUsers, errors),
        conversions: toCount(`${at} treatment conversions`, r.treatmentConversions, errors),
      },
    };
    if (seg.control.conversions > seg.control.users) errors.push(`${at}: control conversions exceed users.`);
    if (seg.treatment.conversions > seg.treatment.users) errors.push(`${at}: treatment conversions exceed users.`);
    segments.push(seg);
  });
  if (segments.length === 0 && errors.length === 0) errors.push('Enter at least one segment.');
  return { segments, errors };
}

/**
 * Parse pasted JSON: either an array of segments or {segments: [...], aggregate_lift?}.
 * Each segment: {dimension, value, control: {users, conversions}, treatment: {users, conversions}}.
 */
export function parseSegmentJson(text: string): { segments: SegmentInput[]; aggregateLift?: number; errors: string[] } {
  let data: unknown;
  try {
    data = JSON.parse(text);
  } catch (e) {
    return { segments: [], errors: [`Invalid JSON: ${(e as Error).message}`] };
  }
  let list: unknown = data;
  let aggregateLift: number | undefined;
  if (data && typeof data === 'object' && !Array.isArray(data)) {
    const obj = data as Record<string, unknown>;
    list = obj.segments;
    if (typeof obj.aggregate_lift === 'number') aggregateLift = obj.aggregate_lift;
  }
  if (!Array.isArray(list)) return { segments: [], errors: ['Expected an array of segments or {"segments": [...]}.'] };
  const errors: string[] = [];
  const segments: SegmentInput[] = list.map((raw, i) => {
    const s = (raw ?? {}) as Record<string, unknown>;
    const c = (s.control ?? {}) as Record<string, unknown>;
    const t = (s.treatment ?? {}) as Record<string, unknown>;
    const at = `Segment ${i + 1}`;
    if (typeof s.dimension !== 'string' || typeof s.value !== 'string') {
      errors.push(`${at}: "dimension" and "value" must be strings.`);
    }
    return {
      dimension: String(s.dimension ?? ''),
      value: String(s.value ?? ''),
      control: { users: toCount(`${at} control.users`, c.users, errors), conversions: toCount(`${at} control.conversions`, c.conversions, errors) },
      treatment: { users: toCount(`${at} treatment.users`, t.users, errors), conversions: toCount(`${at} treatment.conversions`, t.conversions, errors) },
    };
  });
  return { segments, aggregateLift, errors };
}

export function segmentsToRows(segments: SegmentInput[]): SegmentRow[] {
  return segments.map((s) => ({
    dimension: s.dimension,
    value: s.value,
    controlUsers: String(s.control.users),
    controlConversions: String(s.control.conversions),
    treatmentUsers: String(s.treatment.users),
    treatmentConversions: String(s.treatment.conversions),
  }));
}
