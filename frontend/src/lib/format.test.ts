import { bpToPct, formatLift, formatPValue, formatRate, healthTone, humanize, pctToBp } from './format';

describe('format', () => {
  it('converts basis points to percent', () => {
    expect(bpToPct(5000)).toBe('50%');
    expect(bpToPct(10000)).toBe('100%');
    expect(bpToPct(250)).toBe('2.5%');
    expect(bpToPct(1)).toBe('0.01%');
    expect(bpToPct(0)).toBe('0%');
    expect(bpToPct(null)).toBe('—');
  });

  it('parses percent into basis points', () => {
    expect(pctToBp('50')).toBe(5000);
    expect(pctToBp('2.5%')).toBe(250);
    expect(pctToBp(100)).toBe(10000);
    expect(pctToBp('101')).toBeNull();
    expect(pctToBp('abc')).toBeNull();
  });

  it('formats rates and signed lifts', () => {
    expect(formatRate(0.101)).toBe('10.1%');
    expect(formatLift(0.228)).toBe('+22.8%');
    expect(formatLift(-0.05)).toBe('−5.0%');
    expect(formatLift(undefined)).toBe('—');
    expect(formatLift(Infinity)).toBe('—');
  });

  it('formats p-values and labels', () => {
    expect(formatPValue(0.00001)).toBe('< 0.0001');
    expect(formatPValue(0.21)).toBe('0.2100');
    expect(humanize('rollback_triggered')).toBe('Rollback triggered');
    expect(humanize('INCREASE_ROLLOUT')).toBe('Increase rollout');
  });

  it('maps health scores to tones', () => {
    expect(healthTone(91)).toBe('good');
    expect(healthTone(68)).toBe('warn');
    expect(healthTone(30)).toBe('bad');
    expect(healthTone(undefined)).toBe('neutral');
  });
});
