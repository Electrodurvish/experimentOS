import { Link, useParams, useSearchParams } from 'react-router-dom';
import { experiments } from '../api';
import { ExperimentHeader } from '../components/ExperimentHeader';
import { RolloutPanel } from '../components/RolloutPanel';
import { ErrorBox, Loading } from '../components/ui';
import { useAsync } from '../lib/useAsync';
import { AskTab } from './tabs/AskTab';
import { AuditTab } from './tabs/AuditTab';
import { DecisionTab } from './tabs/DecisionTab';
import { HealthTab } from './tabs/HealthTab';
import { OverviewTab } from './tabs/OverviewTab';
import { ProductionTab } from './tabs/ProductionTab';
import { SegmentsTab } from './tabs/SegmentsTab';
import { TimelineTab } from './tabs/TimelineTab';

const TABS = [
  { id: 'overview', label: 'Overview' },
  { id: 'segments', label: 'Segments' },
  { id: 'health', label: 'Health' },
  { id: 'production', label: 'Production' },
  { id: 'decision', label: 'Decision' },
  { id: 'rollout', label: 'Rollout' },
  { id: 'timeline', label: 'Timeline' },
  { id: 'audit', label: 'Audit' },
  { id: 'ask', label: 'Ask AI' },
] as const;
type TabId = (typeof TABS)[number]['id'];

export function ExperimentDetailPage() {
  const { id = '' } = useParams();
  const [params, setParams] = useSearchParams();
  const tabParam = params.get('tab') as TabId | null;
  const tab: TabId = TABS.some((t) => t.id === tabParam) ? (tabParam as TabId) : 'overview';

  const exp = useAsync(() => experiments.get(id), `exp-${id}`);
  const results = useAsync(() => experiments.results(id), `results-${id}`);
  const health = useAsync(() => experiments.health(id), `health-${id}`);

  if (exp.loading && !exp.data) return <Loading />;
  if (!exp.data) return <ErrorBox error={exp.error ?? new Error('Experiment not found.')} onRetry={exp.reload} />;
  const experiment = exp.data;

  const reloadAll = () => {
    exp.reload();
    health.reload();
  };

  return (
    <div className="page">
      <nav className="crumbs">
        <Link to="/experiments">Experiments</Link> / <span className="mono">{experiment.key}</span>
      </nav>
      <ExperimentHeader
        experiment={experiment}
        results={results.data}
        healthScore={health.data?.health.overall_score}
        healthLoading={health.loading}
        onChanged={(e) => {
          exp.setData(e);
          health.reload();
        }}
      />

      <div className="tabs" role="tablist" aria-label="Experiment sections">
        {TABS.map((t) => (
          <button
            key={t.id}
            type="button"
            role="tab"
            aria-selected={tab === t.id}
            className={tab === t.id ? 'tab active' : 'tab'}
            onClick={() => {
              const p = new URLSearchParams(params);
              p.set('tab', t.id);
              setParams(p, { replace: true });
            }}
          >
            {t.label}
          </button>
        ))}
      </div>

      <div role="tabpanel">
        {tab === 'overview' && (
          <OverviewTab experiment={experiment} results={results.data} resultsError={results.error} resultsLoading={results.loading} />
        )}
        {tab === 'segments' && <SegmentsTab experiment={experiment} />}
        {tab === 'health' && <HealthTab experiment={experiment} />}
        {tab === 'production' && <ProductionTab experiment={experiment} />}
        {tab === 'decision' && <DecisionTab experiment={experiment} onChanged={reloadAll} />}
        {tab === 'rollout' && <RolloutPanel experiment={experiment} onChanged={reloadAll} />}
        {tab === 'timeline' && <TimelineTab experiment={experiment} />}
        {tab === 'audit' && <AuditTab experiment={experiment} />}
        {tab === 'ask' && <AskTab experiment={experiment} />}
      </div>
    </div>
  );
}
