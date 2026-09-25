// Presentation helpers. Rollout and traffic values from the backend are basis points
// (0–10000, so 5000 = 50%); conversion rates and lifts are fractions (0.124 = 12.4%).

function trimZeros(s: string): string {
  return s.includes('.') ? s.replace(/\.?0+$/, '') : s;
}

/** 5000 → "50%", 250 → "2.5%", 1 → "0.01%". */
export function bpToPct(bp: number | null | undefined): string {
  if (bp === null || bp === undefined || Number.isNaN(bp)) return '—';
  return `${trimZeros((bp / 100).toFixed(2))}%`;
}

/** "50" or "2.5" → 5000 / 250. Returns null for invalid input. */
export function pctToBp(pct: string | number): number | null {
  const n = typeof pct === 'number' ? pct : Number(String(pct).trim().replace(/%$/, ''));
  if (!Number.isFinite(n) || n < 0 || n > 100) return null;
  return Math.round(n * 100);
}

/** 0.1234 → "12.3%". */
export function formatRate(rate: number | null | undefined, digits = 1): string {
  if (rate === null || rate === undefined || !Number.isFinite(rate)) return '—';
  return `${(rate * 100).toFixed(digits)}%`;
}

/** Relative lift 0.228 → "+22.8%", -0.05 → "−5.0%". */
export function formatLift(lift: number | null | undefined, digits = 1): string {
  if (lift === null || lift === undefined || !Number.isFinite(lift)) return '—';
  const v = lift * 100;
  const sign = v > 0 ? '+' : v < 0 ? '−' : '';
  return `${sign}${Math.abs(v).toFixed(digits)}%`;
}

/** Already-percent change (e.g. change_pct = 12.5) → "+12.5%". */
export function formatSignedPct(pct: number | null | undefined, digits = 1): string {
  if (pct === null || pct === undefined || !Number.isFinite(pct)) return '—';
  const sign = pct > 0 ? '+' : pct < 0 ? '−' : '';
  return `${sign}${Math.abs(pct).toFixed(digits)}%`;
}

export function formatPValue(p: number | null | undefined): string {
  if (p === null || p === undefined || !Number.isFinite(p)) return '—';
  if (p < 0.0001) return '< 0.0001';
  return p.toFixed(4);
}

export function formatNumber(n: number | null | undefined, digits = 0): string {
  if (n === null || n === undefined || !Number.isFinite(n)) return '—';
  return n.toLocaleString(undefined, { maximumFractionDigits: digits });
}

export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return '—';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString(undefined, {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

export function formatTime(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' });
}

export function formatDay(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleDateString(undefined, { weekday: 'short', month: 'short', day: 'numeric', year: 'numeric' });
}

/** "rollback_triggered" / "INCREASE_ROLLOUT" → "Rollback triggered" / "Increase rollout". */
export function humanize(s: string | null | undefined): string {
  if (!s) return '';
  const words = s.replace(/[_-]+/g, ' ').trim().toLowerCase();
  return words.charAt(0).toUpperCase() + words.slice(1);
}

export type Tone = 'good' | 'warn' | 'bad' | 'neutral' | 'info';

export function healthTone(score: number | null | undefined): Tone {
  if (score === null || score === undefined) return 'neutral';
  if (score >= 80) return 'good';
  if (score >= 60) return 'warn';
  return 'bad';
}

const TYPE_LABELS: Record<string, string> = {
  AB: 'A/B Test',
  MULTIVARIATE: 'Multivariate',
  FEATURE_ROLLOUT: 'Feature Rollout',
  HOLDOUT: 'Holdout',
};

export function typeLabel(type: string): string {
  return TYPE_LABELS[type] ?? type;
}

const REC_TONE: Record<string, Tone> = {
  CONTINUE: 'info',
  INCREASE_ROLLOUT: 'good',
  COMPLETE: 'good',
  PAUSE: 'warn',
  DECREASE_ROLLOUT: 'warn',
  ROLLBACK: 'bad',
};

export function recommendationTone(rec: string): Tone {
  return REC_TONE[rec] ?? 'neutral';
}

/** `<input type="datetime-local">` value (local wall time) → ISO-8601 UTC, or null. */
export function localInputToIso(value: string): string | null {
  if (!value) return null;
  const d = new Date(value);
  return Number.isNaN(d.getTime()) ? null : d.toISOString();
}

export function nowLocalInput(): string {
  const d = new Date();
  d.setSeconds(0, 0);
  return new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString().slice(0, 16);
}
