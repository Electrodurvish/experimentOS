import { Link } from 'react-router-dom';
import { experiments, type Experiment, type ExperimentResults } from '../../api';
import { useCanEdit } from '../../auth/context';
import { ConversionChart } from '../../components/ConversionChart';
import { EvidenceList } from '../../components/Evidence';
import { TimeTravel } from '../../components/TimeTravel';
import { Badge, Card, Empty, ErrorBox, GeneratedBy, Loading } from '../../components/ui';
import { bpToPct, formatDateTime, formatLift, formatNumber, formatPValue, formatRate, typeLabel } from '../../lib/format';
import { splitArms } from '../../lib/results';
import { useAsync } from '../../lib/useAsync';

export function OverviewTab({
  experiment,
  results,
  resultsError,
  resultsLoading,
}: {
  experiment: Experiment;
  results?: ExperimentResults;
  resultsError: unknown;
  resultsLoading: boolean;
}) {
  const canEdit = useCanEdit(experiment.organization);
  const arms = splitArms(results, experiment);
  const explain = useAsync(() => experiments.explain(experiment.id), `explain-${experiment.id}`);
  const versions = useAsync(() => experiments.versions(experiment.id), `versions-${experiment.id}`);
  const version = experiment.current_version;
  const variants = results?.variants ?? {};
  const hasData = Object.keys(variants).length > 0;

  return (
    <div className="stack">
      <Card title="Results">
        {resultsLoading && <Loading label="Loading results…" />}
        <ErrorBox error={resultsError} />
        {!resultsLoading && !resultsError && !hasData && <Empty>No exposure or conversion data yet.</Empty>}
        {hasData && (
          <>
            {results?.srm?.is_mismatch && (
              <div className="notice notice-error">
                <strong>Sample ratio mismatch</strong> (χ² = {results.srm.chi_squared.toFixed(2)}, p = {formatPValue(results.srm.p_value)}). Traffic
                split deviates from expected — results may be biased.
              </div>
            )}
            <div className="table-wrap">
              <table className="table">
                <thead>
                  <tr>
                    <th>Variant</th>
                    <th className="num">Users</th>
                    <th className="num hide-sm">Conversions</th>
                    <th className="num">Rate</th>
                    <th className="num hide-sm">95% CI</th>
                    <th className="num">Lift</th>
                    <th className="num">p-value</th>
                  </tr>
                </thead>
                <tbody>
                  {Object.entries(variants).map(([key, v]) => (
                    <tr key={key}>
                      <td>
                        <span className="mono">{key}</span> {key === arms.control?.key && <Badge>control</Badge>}
                      </td>
                      <td className="num">{formatNumber(v.unique_users)}</td>
                      <td className="num hide-sm">{formatNumber(v.conversions)}</td>
                      <td className="num">{formatRate(v.conversion_rate, 2)}</td>
                      <td className="num hide-sm muted">
                        {formatRate(v.ci_lower, 2)} – {formatRate(v.ci_upper, 2)}
                      </td>
                      <td className={`num ${v.lift === undefined ? '' : v.lift >= 0 ? 'pos' : 'neg'}`}>{formatLift(v.lift)}</td>
                      <td className="num">
                        {formatPValue(v.p_value)}{' '}
                        {v.is_significant !== undefined && (
                          <Badge tone={v.is_significant ? 'good' : 'neutral'}>{v.is_significant ? 'significant' : 'n.s.'}</Badge>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <ConversionChart variants={variants} controlKey={arms.control?.key} />
            {!!results?.recommended_sample_size_per_variant && (
              <p className="muted small">
                Recommended sample size: {formatNumber(results.recommended_sample_size_per_variant)} users per variant.
              </p>
            )}
          </>
        )}
      </Card>

      <TimeTravel experiment={experiment} />

      <Card title="AI explanation" actions={<GeneratedBy by={explain.data?.generated_by} model={explain.data?.model} />}>
        {explain.loading && <Loading label="Generating explanation…" />}
        <ErrorBox error={explain.error} feature="Explain" onRetry={explain.reload} />
        {explain.data && (
          <div className="stack-sm">
            {explain.data.summary && <p className="lead">{explain.data.summary}</p>}
            {explain.data.explanation && <p className="prewrap">{explain.data.explanation}</p>}
            <EvidenceList evidence={explain.data.evidence ?? []} cited={explain.data.cited_evidence} />
          </div>
        )}
      </Card>

      <Card
        title="Configuration"
        actions={
          canEdit && (
            <Link to={`/experiments/${experiment.id}/versions/new`} className="btn btn-small">
              Edit variants
            </Link>
          )
        }
      >
        <dl className="kv">
          <dt>Type</dt>
          <dd>{typeLabel(experiment.experiment_type)}</dd>
          <dt>Hypothesis</dt>
          <dd>{experiment.hypothesis || <span className="muted">—</span>}</dd>
          {experiment.description && (
            <>
              <dt>Description</dt>
              <dd>{experiment.description}</dd>
            </>
          )}
          <dt>Started</dt>
          <dd>{formatDateTime(experiment.started_at)}</dd>
          <dt>Version</dt>
          <dd>
            v{version?.version_number ?? '—'} · allocation {bpToPct(version?.traffic_allocation)} {version?.is_locked && <Badge>locked</Badge>}
          </dd>
        </dl>
        {version && version.variants.length > 0 ? (
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th>Variant</th>
                  <th className="num">Share</th>
                  <th className="num">Buckets</th>
                </tr>
              </thead>
              <tbody>
                {[...version.variants]
                  .sort((a, b) => a.bucket_start - b.bucket_start)
                  .map((v) => (
                    <tr key={v.id ?? v.key}>
                      <td>
                        <span className="mono">{v.key}</span> {v.is_control && <Badge>control</Badge>}
                        <div className="muted small">{v.name}</div>
                      </td>
                      <td className="num">{bpToPct(v.traffic_percentage)}</td>
                      <td className="num mono">
                        {v.bucket_start}–{v.bucket_end}
                      </td>
                    </tr>
                  ))}
              </tbody>
            </table>
          </div>
        ) : (
          <Empty>No variants configured. {canEdit && <Link to={`/experiments/${experiment.id}/versions/new`}>Configure variants</Link>}</Empty>
        )}
        {versions.data && versions.data.length > 1 && (
          <details className="details">
            <summary>Version history ({versions.data.length})</summary>
            <ul className="plain-list">
              {[...versions.data]
                .sort((a, b) => b.version_number - a.version_number)
                .map((v) => (
                  <li key={v.id}>
                    v{v.version_number} · {v.variants.map((x) => `${x.key} ${bpToPct(x.traffic_percentage)}`).join(', ') || 'no variants'} ·{' '}
                    <span className="muted">{formatDateTime(v.created_at)}</span>
                  </li>
                ))}
            </ul>
          </details>
        )}
      </Card>
    </div>
  );
}
