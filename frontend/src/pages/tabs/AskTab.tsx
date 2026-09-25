import { useState, type FormEvent } from 'react';
import { experiments, type AskResponse, type Experiment } from '../../api';
import { EvidenceList } from '../../components/Evidence';
import { Card, ErrorBox, GeneratedBy } from '../../components/ui';
import { useAction } from '../../lib/useAsync';

const SUGGESTIONS = ['Why was this recommendation made?', 'Is it safe to increase rollout?', 'Which segment drives the lift?'];

interface Turn {
  question: string;
  response: AskResponse;
}

export function AskTab({ experiment }: { experiment: Experiment }) {
  const [question, setQuestion] = useState('');
  const [turns, setTurns] = useState<Turn[]>([]);
  const ask = useAction(experiments.ask);

  async function submit(e?: FormEvent, q = question) {
    e?.preventDefault();
    const text = q.trim();
    if (!text) return;
    const response = await ask.run(experiment.id, text);
    if (response) {
      setTurns((t) => [{ question: text, response }, ...t]);
      setQuestion('');
    }
  }

  return (
    <div className="stack">
      <Card title={`Ask about ${experiment.key}`}>
        <form className="ask-form" onSubmit={submit}>
          <input
            aria-label="Question"
            placeholder="Ask a question about this experiment…"
            value={question}
            maxLength={1000}
            onChange={(e) => setQuestion(e.target.value)}
          />
          <button type="submit" className="btn btn-primary" disabled={ask.busy || !question.trim()}>
            {ask.busy ? 'Thinking…' : 'Ask'}
          </button>
        </form>
        <div className="chips">
          {SUGGESTIONS.map((s) => (
            <button key={s} type="button" className="chip" disabled={ask.busy} onClick={() => void submit(undefined, s)}>
              {s}
            </button>
          ))}
        </div>
        <ErrorBox error={ask.error} feature="Ask AI" />
      </Card>
      {turns.map((t, i) => (
        <Card key={turns.length - i} title={t.question} actions={<GeneratedBy by={t.response.generated_by} model={t.response.model} />}>
          <p className="prewrap">{t.response.answer}</p>
          {t.response.evidence?.length > 0 && (
            <>
              <h3 className="subhead">Evidence {t.response.cited_evidence?.length ? `(cited: ${t.response.cited_evidence.join(', ')})` : ''}</h3>
              <EvidenceList evidence={t.response.evidence} cited={t.response.cited_evidence} />
            </>
          )}
        </Card>
      ))}
    </div>
  );
}
