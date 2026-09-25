// Client-side mirror of apps/experiments/validators.py::validate_variant_buckets.
import type { Variant } from '../api/types';

export const BUCKET_SPACE = 10000;

export interface VariantDraft {
  key: string;
  name: string;
  description?: string;
  is_control: boolean;
  traffic_percentage: number;
  bucket_start: number;
  bucket_end: number;
  payload?: Record<string, unknown>;
}

/**
 * Returns a list of human-readable problems; empty means the backend will accept the buckets.
 * Rules: exactly one control, unique non-empty keys, integer ranges with start <= end,
 * contiguous from 0 to traffic_allocation - 1 with no overlaps or gaps, and the sum of
 * traffic_percentage equal to traffic_allocation.
 */
export function validateVariants(variants: VariantDraft[], trafficAllocation: number): string[] {
  const errors: string[] = [];
  if (!Number.isInteger(trafficAllocation) || trafficAllocation < 1 || trafficAllocation > BUCKET_SPACE) {
    errors.push(`Traffic allocation must be an integer between 1 and ${BUCKET_SPACE} basis points.`);
    return errors;
  }
  if (variants.length === 0) {
    errors.push('Add at least one variant.');
    return errors;
  }

  const controls = variants.filter((v) => v.is_control);
  if (controls.length !== 1) errors.push('Exactly one variant must be marked as control.');

  const keys = new Set<string>();
  for (const v of variants) {
    const key = v.key.trim();
    if (!key) errors.push('Every variant needs a key.');
    else if (keys.has(key)) errors.push(`Duplicate variant key '${key}'.`);
    keys.add(key);
    if (!v.name.trim()) errors.push(`Variant '${key || '?'}' needs a name.`);
    for (const [field, value] of [
      ['bucket_start', v.bucket_start],
      ['bucket_end', v.bucket_end],
      ['traffic_percentage', v.traffic_percentage],
    ] as const) {
      if (!Number.isInteger(value) || value < 0) {
        errors.push(`Variant '${key || '?'}': ${field} must be a non-negative integer.`);
      }
    }
  }
  if (errors.length) return errors;

  const sorted = [...variants].sort((a, b) => a.bucket_start - b.bucket_start);
  for (const v of sorted) {
    if (v.bucket_start > v.bucket_end) {
      errors.push(`Variant '${v.key}': bucket_start (${v.bucket_start}) must be <= bucket_end (${v.bucket_end}).`);
    }
    if (v.bucket_end >= trafficAllocation) {
      errors.push(`Variant '${v.key}': bucket_end (${v.bucket_end}) exceeds traffic allocation (${trafficAllocation}).`);
    }
  }
  for (let i = 0; i < sorted.length - 1; i++) {
    const cur = sorted[i]!;
    const next = sorted[i + 1]!;
    if (cur.bucket_end >= next.bucket_start) {
      errors.push(`Bucket ranges overlap between '${cur.key}' (ends at ${cur.bucket_end}) and '${next.key}' (starts at ${next.bucket_start}).`);
    } else if (cur.bucket_end + 1 !== next.bucket_start) {
      errors.push(`Gap between '${cur.key}' and '${next.key}' (buckets ${cur.bucket_end + 1}–${next.bucket_start - 1} unassigned).`);
    }
  }
  if (sorted[0]!.bucket_start !== 0) errors.push('Bucket ranges must start at 0.');
  if (sorted[sorted.length - 1]!.bucket_end !== trafficAllocation - 1) {
    errors.push(`Bucket ranges must cover up to ${trafficAllocation - 1}.`);
  }
  const total = variants.reduce((s, v) => s + v.traffic_percentage, 0);
  if (total !== trafficAllocation) {
    errors.push(`Sum of variant traffic_percentage (${total}) must equal traffic_allocation (${trafficAllocation}).`);
  }
  return errors;
}

/**
 * Recompute contiguous bucket ranges from each variant's traffic_percentage, in list order.
 * Any rounding remainder goes to the last variant so the ranges always end at allocation - 1.
 */
export function assignBuckets(variants: VariantDraft[], trafficAllocation: number): VariantDraft[] {
  let start = 0;
  const totalWeight = variants.reduce((s, v) => s + Math.max(0, v.traffic_percentage), 0);
  return variants.map((v, i) => {
    const isLast = i === variants.length - 1;
    let width: number;
    if (isLast) width = trafficAllocation - start;
    else if (totalWeight > 0) width = Math.round((Math.max(0, v.traffic_percentage) / totalWeight) * trafficAllocation);
    else width = Math.floor(trafficAllocation / variants.length);
    width = Math.max(0, Math.min(width, trafficAllocation - start));
    const out = { ...v, traffic_percentage: width, bucket_start: start, bucket_end: start + width - 1 };
    start += width;
    return out;
  });
}

/** Split the allocation evenly across n variants (first is control). */
export function evenSplit(keys: string[], trafficAllocation: number): VariantDraft[] {
  const drafts = keys.map((key, i) => ({
    key,
    name: key.charAt(0).toUpperCase() + key.slice(1),
    is_control: i === 0,
    traffic_percentage: 1,
    bucket_start: 0,
    bucket_end: 0,
  }));
  return assignBuckets(drafts, trafficAllocation);
}

export function draftsFromVariants(variants: Variant[]): VariantDraft[] {
  return [...variants]
    .sort((a, b) => a.bucket_start - b.bucket_start)
    .map(({ id: _id, ...rest }) => ({ ...rest }));
}

/** Client-side key hygiene for experiment and variant keys (the backend only enforces max length). */
export const KEY_PATTERN = /^[A-Za-z0-9][A-Za-z0-9_.-]*$/;

/** Lay out contiguous ranges in list order using each variant's traffic_percentage as its width. */
export function layoutBuckets(variants: VariantDraft[]): VariantDraft[] {
  let start = 0;
  return variants.map((v) => {
    const width = Math.max(0, Math.round(v.traffic_percentage));
    const out = { ...v, traffic_percentage: width, bucket_start: start, bucket_end: start + width - 1 };
    start += width;
    return out;
  });
}
