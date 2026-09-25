import { useEffect, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import {
  EXPERIMENT_STATUSES,
  EXPERIMENT_TYPE_LABELS,
  EXPERIMENT_TYPES,
  experiments,
  projects,
  type ExperimentType,
} from '../api';
import { useAuth } from '../auth/context';
import { RolloutBar } from '../components/RolloutBar';
import { Card, Empty, ErrorBox, HealthBadge, Loading, Pagination, StatusBadge } from '../components/ui';
import { formatDateTime } from '../lib/format';
import { useAsync } from '../lib/useAsync';
import { useHealthScores } from '../lib/useHealthScores';

export function ExperimentsPage() {
  const { canEdit } = useAuth();
  const [params, setParams] = useSearchParams();
  const status = params.get('status') ?? '';
  const type = params.get('type') ?? '';
  const project = params.get('project') ?? '';
  const search = params.get('q') ?? '';
  const page = Number(params.get('page') ?? '1') || 1;
  const [searchDraft, setSearchDraft] = useState(search);
  useEffect(() => setSearchDraft(search), [search]);

  const projectList = useAsync(() => projects.list(), 'projects');
  const list = useAsync(
    () => experiments.list({ status, experiment_type: type, project, search, page }),
    JSON.stringify({ status, type, project, search, page }),
  );
  const rows = list.data?.results ?? [];
  const { scores } = useHealthScores(rows.filter((e) => e.status === 'RUNNING' || e.status === 'PAUSED').map((e) => e.id));

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
        <h1>Experiments</h1>
        {canEdit && (
          <Link to="/experiments/new" className="btn btn-primary">
            New experiment
          </Link>
        )}
      </div>

      <form
        className="filters"
        onSubmit={(e) => {
          e.preventDefault();
          update({ q: searchDraft.trim() });
        }}
      >
        <input
          type="search"
          placeholder="Search key or name…"
          aria-label="Search experiments"
          value={searchDraft}
          onChange={(e) => setSearchDraft(e.target.value)}
        />
        <select aria-label="Status" value={status} onChange={(e) => update({ status: e.target.value })}>
          <option value="">All statuses</option>
          {EXPERIMENT_STATUSES.map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </select>
        <select aria-label="Type" value={type} onChange={(e) => update({ type: e.target.value })}>
          <option value="">All types</option>
          {EXPERIMENT_TYPES.map((t) => (
            <option key={t} value={t}>
              {EXPERIMENT_TYPE_LABELS[t]}
            </option>
          ))}
        </select>
        <select aria-label="Project" value={project} onChange={(e) => update({ project: e.target.value })}>
          <option value="">All projects</option>
          {projectList.data?.results.map((p) => (
            <option key={p.id} value={p.id}>
              {p.name}
            </option>
          ))}
        </select>
        <button type="submit" className="btn">
          Search
        </button>
      </form>

      <Card>
        {list.loading && <Loading />}
        <ErrorBox error={list.error} onRetry={list.reload} />
        {!list.loading && !list.error && rows.length === 0 && <Empty>No experiments match these filters.</Empty>}
        {rows.length > 0 && (
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th>Experiment</th>
                  <th>Status</th>
                  <th className="hide-sm">Type</th>
                  <th>Rollout</th>
                  <th className="hide-sm">Health</th>
                  <th className="hide-sm">Updated</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((e) => (
                  <tr key={e.id}>
                    <td>
                      <Link to={`/experiments/${e.id}`} className="mono">
                        {e.key}
                      </Link>
                      <div className="muted small">{e.name}</div>
                    </td>
                    <td>
                      <StatusBadge status={e.status} />
                    </td>
                    <td className="hide-sm">{EXPERIMENT_TYPE_LABELS[e.experiment_type as ExperimentType] ?? e.experiment_type}</td>
                    <td className="cell-rollout">
                      <RolloutBar bp={e.rollout_percentage} />
                    </td>
                    <td className="hide-sm">{e.id in scores ? <HealthBadge score={scores[e.id]} /> : <span className="muted">—</span>}</td>
                    <td className="hide-sm muted small">{formatDateTime(e.updated_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {list.data && <Pagination page={page} count={list.data.count} onPage={(p) => update({ page: String(p) })} />}
      </Card>
    </div>
  );
}
