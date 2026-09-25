import { useSearchParams } from 'react-router-dom';
import { audit, experiments } from '../api';
import { AuditTable } from '../components/AuditTable';
import { Card, Empty, ErrorBox, Loading, Pagination } from '../components/ui';
import { useAsync } from '../lib/useAsync';

const COMMON_ACTIONS = ['experiment_created', 'version_created', 'status_changed', 'rollout_changed', 'decision_made'];

export function AuditLogsPage() {
  const [params, setParams] = useSearchParams();
  const experiment = params.get('experiment') ?? '';
  const action = params.get('action') ?? '';
  const page = Number(params.get('page') ?? '1') || 1;

  const expList = useAsync(() => experiments.list({ ordering: '-updated_at' }), 'audit-exps');
  const logs = useAsync(() => audit.list({ experiment, action, page }), JSON.stringify({ experiment, action, page }));
  const keys = Object.fromEntries((expList.data?.results ?? []).map((e) => [e.id, e.key]));

  function update(next: Record<string, string>) {
    const p = new URLSearchParams(params);
    for (const [k, v] of Object.entries(next)) {
      if (v) p.set(k, v);
      else p.delete(k);
    }
    if (!('page' in next)) p.delete('page');
    setParams(p);
  }

  return (
    <div className="page">
      <div className="page-header">
        <h1>Audit Logs</h1>
      </div>
      <div className="filters">
        <select aria-label="Experiment" value={experiment} onChange={(e) => update({ experiment: e.target.value })}>
          <option value="">All experiments</option>
          {expList.data?.results.map((e) => (
            <option key={e.id} value={e.id}>
              {e.key}
            </option>
          ))}
        </select>
        <input
          list="audit-actions"
          aria-label="Action"
          placeholder="Action (exact), e.g. version_created"
          defaultValue={action}
          onKeyDown={(e) => {
            if (e.key === 'Enter') update({ action: e.currentTarget.value.trim() });
          }}
          onBlur={(e) => {
            if (e.currentTarget.value.trim() !== action) update({ action: e.currentTarget.value.trim() });
          }}
        />
        <datalist id="audit-actions">
          {COMMON_ACTIONS.map((a) => (
            <option key={a} value={a} />
          ))}
        </datalist>
      </div>
      <Card>
        {logs.loading && <Loading />}
        <ErrorBox error={logs.error} onRetry={logs.reload} />
        {logs.data && logs.data.results.length === 0 && <Empty>No audit entries match.</Empty>}
        {logs.data && <AuditTable logs={logs.data.results} experimentKeys={keys} />}
        {logs.data && <Pagination page={page} count={logs.data.count} onPage={(p) => update({ page: String(p) })} />}
      </Card>
    </div>
  );
}
