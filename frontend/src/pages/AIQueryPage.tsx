import { useState, type FormEvent } from 'react';
import { Link } from 'react-router-dom';
import { ai, type AIQueryResponse } from '../api';
import { Card, ErrorBox, GeneratedBy, StatusBadge } from '../components/ui';
import { useAction } from '../lib/useAsync';

const EXAMPLES = [
  'Which running experiments have a health score below 70?',
  'Which experiments were rolled back this week?',
  'What is the best performing checkout experiment?',
];

export function AIQueryPage() {
  const [question, setQuestion] = useState('');
  const [history, setHistory] = useState<{ q: string; r: AIQueryResponse }[]>([]);
  const query = useAction(ai.query);

  async function submit(e?: FormEvent, q = question) {
    e?.preventDefault();
    const text = q.trim();
    if (!text) return;
    const r = await query.run(text);
    if (r) {
      setHistory((h) => [{ q: text, r }, ...h]);
      setQuestion('');
    }
  }

  return (
    <div className="page page-narrow">
      <div className="page-header">
        <h1>Ask AI</h1>
      </div>
      <Card>
        <p className="muted">Ask questions across all experiments. For one experiment, use its “Ask AI” tab.</p>
        <form className="ask-form" onSubmit={submit}>
          <input aria-label="Question" placeholder="Ask about your experiments…" value={question} maxLength={1000} onChange={(e) => setQuestion(e.target.value)} />
          <button type="submit" className="btn btn-primary" disabled={query.busy || !question.trim()}>
            {query.busy ? 'Thinking…' : 'Ask'}
          </button>
        </form>
        <div className="chips">
          {EXAMPLES.map((x) => (
            <button key={x} type="button" className="chip" disabled={query.busy} onClick={() => void submit(undefined, x)}>
              {x}
            </button>
          ))}
        </div>
        <ErrorBox error={query.error} feature="AI query" />
      </Card>
      {history.map((h, i) => (
        <Card key={history.length - i} title={h.q} actions={<GeneratedBy by={h.r.generated_by} model={h.r.model} />}>
          <p className="prewrap">{h.r.answer}</p>
          {h.r.experiments?.length > 0 && (
            <ul className="plain-list">
              {h.r.experiments.map((e) => (
                <li key={e.id}>
                  <Link to={`/experiments/${e.id}`} className="mono">
                    {e.key}
                  </Link>{' '}
                  <StatusBadge status={e.status} />
                </li>
              ))}
            </ul>
          )}
        </Card>
      ))}
    </div>
  );
}
