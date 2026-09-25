export interface ExplanationLine {
  status: 'pass' | 'fail' | 'info';
  text: string;
}

/** Split a backend checklist line ("✓ …", "✗ …", "• …") into status and text. */
export function parseExplanationLine(line: string): ExplanationLine {
  const trimmed = line.trim();
  const mark = trimmed.charAt(0);
  const rest = trimmed.slice(1).trim();
  if (mark === '✓') return { status: 'pass', text: rest };
  if (mark === '✗' || mark === '✘') return { status: 'fail', text: rest };
  if (mark === '•') return { status: 'info', text: rest };
  return { status: 'info', text: trimmed };
}

/** Parse an optional JSON-object text field. Empty → undefined. */
export function parseContext(text: string): { value?: Record<string, unknown>; error?: string } {
  if (!text.trim()) return {};
  try {
    const parsed: unknown = JSON.parse(text);
    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) return { error: 'Context must be a JSON object.' };
    return { value: parsed as Record<string, unknown> };
  } catch (e) {
    return { error: `Invalid JSON: ${(e as Error).message}` };
  }
}
