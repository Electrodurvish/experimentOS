import { assignBuckets, evenSplit, layoutBuckets, validateVariants, type VariantDraft } from './buckets';

const v = (key: string, start: number, end: number, control = false, pct?: number): VariantDraft => ({
  key,
  name: key,
  is_control: control,
  bucket_start: start,
  bucket_end: end,
  traffic_percentage: pct ?? end - start + 1,
});

describe('validateVariants', () => {
  it('accepts a contiguous 50/50 split', () => {
    expect(validateVariants([v('control', 0, 4999, true), v('treatment', 5000, 9999)], 10000)).toEqual([]);
  });

  it('accepts a partial allocation that covers 0..allocation-1', () => {
    expect(validateVariants([v('control', 0, 2499, true), v('treatment', 2500, 4999)], 5000)).toEqual([]);
  });

  it('requires exactly one control', () => {
    expect(validateVariants([v('a', 0, 4999), v('b', 5000, 9999)], 10000)).toContain('Exactly one variant must be marked as control.');
    expect(validateVariants([v('a', 0, 4999, true), v('b', 5000, 9999, true)], 10000)).toContain(
      'Exactly one variant must be marked as control.',
    );
  });

  it('detects gaps, overlaps and bad bounds', () => {
    const gap = validateVariants([v('control', 0, 4000, true), v('t', 5000, 9999, false, 5999)], 10000);
    expect(gap.some((e) => e.startsWith('Gap between'))).toBe(true);

    const overlap = validateVariants([v('control', 0, 5000, true), v('t', 5000, 9999, false, 4999)], 10000);
    expect(overlap.some((e) => e.startsWith('Bucket ranges overlap'))).toBe(true);

    const notZero = validateVariants([v('control', 1, 4999, true, 5000), v('t', 5000, 9999)], 10000);
    expect(notZero).toContain('Bucket ranges must start at 0.');

    const tooFar = validateVariants([v('control', 0, 4999, true), v('t', 5000, 10000, false, 5000)], 10000);
    expect(tooFar.some((e) => e.includes('exceeds traffic allocation'))).toBe(true);

    const short = validateVariants([v('control', 0, 4999, true), v('t', 5000, 9000, false, 5000)], 10000);
    expect(short).toContain('Bucket ranges must cover up to 9999.');
  });

  it('checks the traffic_percentage sum and duplicate keys', () => {
    const sum = validateVariants([v('control', 0, 4999, true, 4000), v('t', 5000, 9999)], 10000);
    expect(sum.some((e) => e.startsWith('Sum of variant traffic_percentage'))).toBe(true);
    const dup = validateVariants([v('x', 0, 4999, true), v('x', 5000, 9999)], 10000);
    expect(dup).toContain("Duplicate variant key 'x'.");
  });
});

describe('bucket helpers', () => {
  it('splits evenly and stays valid', () => {
    const drafts = evenSplit(['control', 'a', 'b'], 10000);
    expect(drafts.map((d) => [d.bucket_start, d.bucket_end])).toEqual([
      [0, 3332],
      [3333, 6665],
      [6666, 9999],
    ]);
    expect(validateVariants(drafts, 10000)).toEqual([]);
  });

  it('scales weights to the allocation', () => {
    const drafts = assignBuckets([v('control', 0, 0, true, 1), v('t', 0, 0, false, 3)], 8000);
    expect(drafts.map((d) => d.traffic_percentage)).toEqual([2000, 6000]);
    expect(validateVariants(drafts, 8000)).toEqual([]);
  });

  it('lays out contiguous ranges from widths', () => {
    const drafts = layoutBuckets([v('control', 0, 0, true, 3000), v('t', 0, 0, false, 7000)]);
    expect(drafts.map((d) => [d.bucket_start, d.bucket_end])).toEqual([
      [0, 2999],
      [3000, 9999],
    ]);
  });
});
