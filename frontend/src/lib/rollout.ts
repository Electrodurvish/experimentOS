import { pctToBp } from './format';

/** Parse "10, 25, 50, 100" (percent) into ascending basis points, or an error message. */
export function parseStages(text: string): { stages: number[]; error: string | null } {
  const parts = text.split(/[,\s]+/).filter(Boolean);
  if (parts.length === 0) return { stages: [], error: 'Enter at least one stage.' };
  const stages: number[] = [];
  for (const p of parts) {
    const bp = pctToBp(p);
    if (bp === null || bp <= 0) return { stages: [], error: `"${p}" is not a percentage in (0, 100].` };
    stages.push(bp);
  }
  for (let i = 1; i < stages.length; i++) {
    if (stages[i]! <= stages[i - 1]!) return { stages: [], error: 'Stages must be strictly ascending.' };
  }
  return { stages, error: null };
}
