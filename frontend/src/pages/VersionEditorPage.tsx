import { useMemo, useState } from 'react';
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom';
import { experiments, type Experiment } from '../api';
import { useAuth } from '../auth/context';
import { Card, ErrorBox, Field, Loading, StatusBadge } from '../components/ui';
import {
  assignBuckets,
  draftsFromVariants,
  evenSplit,
  KEY_PATTERN,
  layoutBuckets,
  validateVariants,
  type VariantDraft,
} from '../lib/buckets';
import { bpToPct, pctToBp } from '../lib/format';
import { useAction, useAsync } from '../lib/useAsync';

interface Row extends VariantDraft {
  payloadText: string;
}

function toRows(drafts: VariantDraft[]): Row[] {
  return drafts.map((d) => ({ ...d, payloadText: d.payload && Object.keys(d.payload).length ? JSON.stringify(d.payload) : '' }));
}

export function VersionEditorPage() {
  const { id = '' } = useParams();
  const [params] = useSearchParams();
  const justCreated = params.get('created') === '1';
  const exp = useAsync(() => experiments.get(id), id);
  if (exp.loading) return <Loading />;
  if (exp.error || !exp.data) return <ErrorBox error={exp.error} onRetry={exp.reload} />;
  return <VersionEditor experiment={exp.data} justCreated={justCreated} />;
}

function VersionEditor({ experiment, justCreated }: { experiment: Experiment; justCreated: boolean }) {
  const { canEdit } = useAuth();
  const navigate = useNavigate();
  const current = experiment.current_version;
  const [allocationPct, setAllocationPct] = useState(() => String((current?.traffic_allocation ?? 10000) / 100));
  const allocation = pctToBp(allocationPct) ?? NaN;
  const [rows, setRows] = useState<Row[]>(() =>
    toRows(current?.variants.length ? draftsFromVariants(current.variants) : evenSplit(['control', 'treatment'], current?.traffic_allocation ?? 10000)),
  );
  const [targetingText, setTargetingText] = useState(() =>
    current?.targeting?.rules_json ? JSON.stringify(current.targeting.rules_json, null, 2) : '',
  );
  const save = useAction(experiments.createVersion);

  const payloadErrors = rows.flatMap((r) => {
    if (!r.payloadText.trim()) return [];
    try {
      const v: unknown = JSON.parse(r.payloadText);
      return v && typeof v === 'object' && !Array.isArray(v) ? [] : [`Variant '${r.key}': payload must be a JSON object.`];
    } catch {
      return [`Variant '${r.key}': payload is not valid JSON.`];
    }
  });
  let targetingError: string | null = null;
  let targeting: unknown = undefined;
  if (targetingText.trim()) {
    try {
      targeting = JSON.parse(targetingText);
    } catch {
      targetingError = 'Targeting rules are not valid JSON.';
    }
  }
  const keyErrors = rows.filter((r) => r.key && !KEY_PATTERN.test(r.key)).map((r) => `Variant key '${r.key}' has invalid characters.`);
  const bucketErrors = useMemo(() => validateVariants(rows, allocation), [rows, allocation]);
  const errors = [...bucketErrors, ...keyErrors, ...payloadErrors, ...(targetingError ? [targetingError] : [])];

  function patch(i: number, change: Partial<Row>, relayout = false) {
    setRows((rs) => {
      const next = rs.map((r, j) => (j === i ? { ...r, ...change } : r));
      return relayout ? (layoutBuckets(next) as Row[]) : next;
    });
  }

  function setControl(i: number) {
    setRows((rs) => rs.map((r, j) => ({ ...r, is_control: j === i })));
  }

  function addVariant() {
    setRows((rs) => {
      const n = rs.length;
      const next = [...rs, { key: `variant_${n}`, name: `Variant ${n}`, is_control: false, traffic_percentage: 0, bucket_start: 0, bucket_end: -1, payloadText: '' }];
      return assignBuckets(next.map((r) => ({ ...r, traffic_percentage: 1 })), Number.isFinite(allocation) ? allocation : 10000).map((d, j) => ({ ...next[j]!, ...d }));
    });
  }

  function removeVariant(i: number) {
    setRows((rs) => layoutBuckets(rs.filter((_, j) => j !== i)) as Row[]);
  }

  function balance() {
    if (!Number.isFinite(allocation)) return;
    setRows((rs) => assignBuckets(rs.map((r) => ({ ...r, traffic_percentage: 1 })), allocation).map((d, j) => ({ ...rs[j]!, ...d })));
  }

  function normalize() {
    if (!Number.isFinite(allocation)) return;
    setRows((rs) => assignBuckets(rs, allocation).map((d, j) => ({ ...rs[j]!, ...d })));
  }

  async function submit() {
    if (errors.length) return;
    const version = await save.run(experiment.id, {
      traffic_allocation: allocation,
      variants: rows.map(({ payloadText, ...r }) => ({
        key: r.key.trim(),
        name: r.name.trim(),
        description: r.description ?? '',
        is_control: r.is_control,
        traffic_percentage: r.traffic_percentage,
        bucket_start: r.bucket_start,
        bucket_end: r.bucket_end,
        payload: payloadText.trim() ? (JSON.parse(payloadText) as Record<string, unknown>) : {},
      })),
      ...(targeting !== undefined ? { targeting: { rules_json: targeting } } : {}),
    });
    if (version) navigate(`/experiments/${experiment.id}`);
  }

  return (
    <div className="page">
      <div className="page-header">
        <div>
          <h1>
            Variants · <span className="mono">{experiment.key}</span>
          </h1>
          <div className="muted small">
            <StatusBadge status={experiment.status} /> Current version v{current?.version_number ?? '—'}. Saving creates a new version.
          </div>
        </div>
        <Link to={`/experiments/${experiment.id}`}>Back to experiment</Link>
      </div>
      {justCreated && (
        <div className="notice notice-good">Experiment created. Configure its variants below to create version 2 with real buckets.</div>
      )}
      {!canEdit && <div className="notice notice-info">Read-only: your role can’t create versions.</div>}

      <Card title="Traffic">
        <div className="form-grid">
          <Field label="Traffic allocation (%)" htmlFor="alloc" hint={`= ${Number.isFinite(allocation) ? `${allocation} basis points; buckets 0–${allocation - 1}` : 'invalid'}`}>
            <input id="alloc" type="number" min={0.01} max={100} step={0.01} value={allocationPct} onChange={(e) => setAllocationPct(e.target.value)} />
          </Field>
          <div className="button-row">
            <button type="button" className="btn" onClick={balance}>
              Split evenly
            </button>
            <button type="button" className="btn" onClick={normalize} title="Scale shares so they sum to the allocation">
              Scale to allocation
            </button>
            <button type="button" className="btn" onClick={addVariant}>
              + Add variant
            </button>
          </div>
        </div>
        <BucketStrip rows={rows} allocation={Number.isFinite(allocation) ? allocation : 10000} />
      </Card>

      <Card title="Variants">
        <div className="variant-list">
          {rows.map((r, i) => (
            <fieldset key={i} className="variant-row">
              <legend className="sr-only">Variant {i + 1}</legend>
              <Field label="Key" htmlFor={`vk-${i}`}>
                <input id={`vk-${i}`} className="mono" value={r.key} onChange={(e) => patch(i, { key: e.target.value })} />
              </Field>
              <Field label="Name" htmlFor={`vn-${i}`}>
                <input id={`vn-${i}`} value={r.name} onChange={(e) => patch(i, { name: e.target.value })} />
              </Field>
              <Field label="Share (%)" htmlFor={`vs-${i}`} hint={`${r.traffic_percentage} bp`}>
                <input
                  id={`vs-${i}`}
                  type="number"
                  min={0}
                  max={100}
                  step={0.01}
                  value={r.traffic_percentage / 100}
                  onChange={(e) => patch(i, { traffic_percentage: pctToBp(e.target.value) ?? 0 }, true)}
                />
              </Field>
              <Field label="Bucket start" htmlFor={`vb-${i}`}>
                <input
                  id={`vb-${i}`}
                  type="number"
                  min={0}
                  max={9999}
                  value={r.bucket_start}
                  onChange={(e) => {
                    const start = Math.trunc(Number(e.target.value));
                    patch(i, { bucket_start: start, traffic_percentage: r.bucket_end - start + 1 });
                  }}
                />
              </Field>
              <Field label="Bucket end" htmlFor={`ve-${i}`}>
                <input
                  id={`ve-${i}`}
                  type="number"
                  min={0}
                  max={9999}
                  value={r.bucket_end}
                  onChange={(e) => {
                    const end = Math.trunc(Number(e.target.value));
                    patch(i, { bucket_end: end, traffic_percentage: end - r.bucket_start + 1 });
                  }}
                />
              </Field>
              <div className="field variant-control">
                <label>
                  <input type="radio" name="control" checked={r.is_control} onChange={() => setControl(i)} /> Control
                </label>
                <button type="button" className="btn btn-small btn-danger-ghost" disabled={rows.length <= 1} onClick={() => removeVariant(i)}>
                  Remove
                </button>
              </div>
              <Field label="Payload (JSON, optional)" htmlFor={`vp-${i}`}>
                <input
                  id={`vp-${i}`}
                  className="mono"
                  placeholder='{"button_color": "green"}'
                  value={r.payloadText}
                  onChange={(e) => patch(i, { payloadText: e.target.value })}
                />
              </Field>
            </fieldset>
          ))}
        </div>
      </Card>

      <Card title="Targeting rules (optional)">
        <textarea
          className="mono"
          rows={5}
          aria-label="Targeting rules JSON"
          placeholder={'{"operator": "AND", "conditions": [\n  {"field": "country", "operator": "in", "value": ["US", "IN"]}\n]}'}
          value={targetingText}
          onChange={(e) => setTargetingText(e.target.value)}
        />
        <p className="muted small">Stored as the version’s rules_json and evaluated by the assignment engine.</p>
      </Card>

      {errors.length > 0 ? (
        <div className="notice notice-error" role="alert">
          <strong>Fix before saving:</strong>
          <ul>
            {errors.map((e) => (
              <li key={e}>{e}</li>
            ))}
          </ul>
        </div>
      ) : (
        <div className="notice notice-good">✓ Buckets are contiguous and cover 0–{allocation - 1}.</div>
      )}
      <ErrorBox error={save.error} />
      {canEdit && (
        <div className="form-actions">
          <button type="button" className="btn btn-primary" disabled={errors.length > 0 || save.busy} onClick={submit}>
            {save.busy ? 'Saving…' : `Create version v${(current?.version_number ?? 0) + 1}`}
          </button>
        </div>
      )}
    </div>
  );
}

function BucketStrip({ rows, allocation }: { rows: Row[]; allocation: number }) {
  return (
    <div className="bucket-strip" aria-label="Bucket layout">
      {rows.map((r, i) => {
        const width = Math.max(0, r.bucket_end - r.bucket_start + 1);
        return (
          <div
            key={i}
            className={`bucket-seg ${r.is_control ? 'control' : ''} seg-${i % 4}`}
            style={{ flexGrow: width, flexBasis: 0 }}
            title={`${r.key}: ${r.bucket_start}–${r.bucket_end} (${bpToPct(width)})`}
          >
            <span>{r.key || '?'}</span>
          </div>
        );
      })}
      {allocation < 10000 && (
        <div className="bucket-seg unallocated" style={{ flexGrow: 10000 - allocation, flexBasis: 0 }} title="Not in experiment">
          <span>excluded</span>
        </div>
      )}
    </div>
  );
}
