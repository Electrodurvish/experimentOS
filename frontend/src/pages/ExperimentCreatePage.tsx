import { useEffect, useState, type FormEvent } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { EXPERIMENT_TYPE_LABELS, EXPERIMENT_TYPES, experiments, projects, type ExperimentType } from '../api';
import { useAuth } from '../auth/context';
import { Card, ErrorBox, Field, Loading } from '../components/ui';
import { KEY_PATTERN } from '../lib/buckets';
import { useAction, useAsync } from '../lib/useAsync';

export function ExperimentCreatePage() {
  const { canEdit, canEditOrg } = useAuth();
  const navigate = useNavigate();
  const projectList = useAsync(() => projects.list(), 'projects');
  const [projectId, setProjectId] = useState('');
  const [key, setKey] = useState('');
  const [name, setName] = useState('');
  const [hypothesis, setHypothesis] = useState('');
  const [description, setDescription] = useState('');
  const [type, setType] = useState<ExperimentType>('AB');
  const [touched, setTouched] = useState(false);
  const create = useAction(experiments.create);

  const firstProject = projectList.data?.results[0]?.id;
  useEffect(() => {
    if (!projectId && firstProject) setProjectId(firstProject);
  }, [projectId, firstProject]);

  const selectedOrg = projectList.data?.results.find((p) => p.id === projectId)?.organization;
  const canCreateHere = canEditOrg(selectedOrg);
  const keyError = key && !KEY_PATTERN.test(key) ? 'Use letters, digits, "_", "-" or "." (no spaces).' : null;
  const valid = !!projectId && canCreateHere && !!key && !keyError && !!name.trim();

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setTouched(true);
    if (!valid) return;
    const created = await create.run({
      project_id: projectId,
      key: key.trim(),
      name: name.trim(),
      hypothesis: hypothesis.trim(),
      description: description.trim(),
      experiment_type: type,
    });
    if (created) navigate(`/experiments/${created.id}/versions/new?created=1`);
  }

  if (!canEdit) {
    return (
      <div className="page">
        <h1>New experiment</h1>
        <div className="notice notice-info">Your role is read-only; ask an admin or experiment manager to create experiments.</div>
      </div>
    );
  }

  return (
    <div className="page page-narrow">
      <div className="page-header">
        <h1>New experiment</h1>
        <Link to="/experiments">Cancel</Link>
      </div>
      <Card>
        {projectList.loading && <Loading label="Loading projects…" />}
        <ErrorBox error={projectList.error} onRetry={projectList.reload} />
        {projectList.data && projectList.data.results.length === 0 && (
          <div className="notice notice-info">No projects exist yet. Create an organization and project via the API first.</div>
        )}
        <form onSubmit={onSubmit} noValidate>
          <Field label="Project" htmlFor="project">
            <select id="project" value={projectId} onChange={(e) => setProjectId(e.target.value)} required>
              <option value="" disabled>
                Select a project
              </option>
              {projectList.data?.results.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}
                </option>
              ))}
            </select>
          </Field>
          {projectId && !canCreateHere && (
            <div className="notice notice-info">Your role in this project’s organization is read-only; pick another project.</div>
          )}
          <Field label="Key" htmlFor="key" hint={keyError ?? 'Used by SDKs to evaluate the experiment, e.g. checkout_v3. Unique within the project.'}>
            <input
              id="key"
              className={keyError || (touched && !key) ? 'invalid' : undefined}
              value={key}
              onChange={(e) => setKey(e.target.value)}
              placeholder="checkout_v3"
              maxLength={255}
              required
            />
          </Field>
          <Field label="Name" htmlFor="name">
            <input
              id="name"
              className={touched && !name.trim() ? 'invalid' : undefined}
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Checkout redesign v3"
              maxLength={255}
              required
            />
          </Field>
          <Field label="Type" htmlFor="type">
            <select id="type" value={type} onChange={(e) => setType(e.target.value as ExperimentType)}>
              {EXPERIMENT_TYPES.map((t) => (
                <option key={t} value={t}>
                  {EXPERIMENT_TYPE_LABELS[t]}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Hypothesis" htmlFor="hypothesis" hint="What do you expect to change, and why?">
            <textarea
              id="hypothesis"
              rows={3}
              value={hypothesis}
              onChange={(e) => setHypothesis(e.target.value)}
              placeholder="A single-page checkout will increase conversion by 5%."
            />
          </Field>
          <Field label="Description" htmlFor="description">
            <textarea id="description" rows={2} value={description} onChange={(e) => setDescription(e.target.value)} />
          </Field>
          <ErrorBox error={create.error} />
          <div className="form-actions">
            <button type="submit" className="btn btn-primary" disabled={create.busy || (touched && !valid)}>
              {create.busy ? 'Creating…' : 'Create & configure variants'}
            </button>
          </div>
        </form>
      </Card>
    </div>
  );
}
