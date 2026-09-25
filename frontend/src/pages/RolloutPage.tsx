import { Link, useSearchParams } from 'react-router-dom';
import { experiments } from '../api';
import { ExperimentHeader } from '../components/ExperimentHeader';
import { RolloutPanel } from '../components/RolloutPanel';
import { Empty, ErrorBox, Loading } from '../components/ui';
import { bpToPct } from '../lib/format';
import { useAsync } from '../lib/useAsync';

export function RolloutPage() {
  const [params, setParams] = useSearchParams();
  const selected = params.get('experiment') ?? '';
  const candidates = useAsync(async () => {
    const [running, paused] = await Promise.all([
      experiments.list({ status: 'RUNNING', page_size: 100 }),
      experiments.list({ status: 'PAUSED', page_size: 100 }),
    ]);
    return [...running.results, ...paused.results];
  }, 'rollout-candidates');
  const exp = useAsync(() => experiments.get(selected), selected ? `rollout-exp-${selected}` : null);

  return (
    <div className="page">
      <div className="page-header">
        <h1>Rollout Control</h1>
      </div>
      <div className="filters">
        <select
          aria-label="Experiment"
          value={selected}
          onChange={(e) => setParams(e.target.value ? { experiment: e.target.value } : {})}
        >
          <option value="">Select a running or paused experiment…</option>
          {candidates.data?.map((e) => (
            <option key={e.id} value={e.id}>
              {e.key} · {e.status} · {bpToPct(e.rollout_percentage)}
            </option>
          ))}
        </select>
      </div>
      {candidates.loading && <Loading />}
      <ErrorBox error={candidates.error} onRetry={candidates.reload} />
      {candidates.data && candidates.data.length === 0 && (
        <Empty>
          No running or paused experiments. <Link to="/experiments">Browse all experiments</Link>.
        </Empty>
      )}
      {selected && exp.loading && !exp.data && <Loading />}
      <ErrorBox error={exp.error} onRetry={exp.reload} />
      {selected && exp.data && exp.data.id === selected && (
        <>
          <ExperimentHeader experiment={exp.data} onChanged={(e) => exp.setData(e)} />
          <p>
            <Link to={`/experiments/${exp.data.id}?tab=decision`}>See the decision engine’s recommendation →</Link>
          </p>
          <RolloutPanel experiment={exp.data} onChanged={exp.reload} />
        </>
      )}
    </div>
  );
}
