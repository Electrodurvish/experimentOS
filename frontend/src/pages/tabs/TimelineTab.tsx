import { experiments, type Experiment } from '../../api';
import { Timeline } from '../../components/Timeline';
import { Card, ErrorBox, Loading } from '../../components/ui';
import { useAsync } from '../../lib/useAsync';

export function TimelineTab({ experiment }: { experiment: Experiment }) {
  const tl = useAsync(() => experiments.timeline(experiment.id), `timeline-${experiment.id}`);
  return (
    <Card
      title="Timeline"
      actions={
        <button type="button" className="btn btn-small" onClick={tl.reload}>
          Refresh
        </button>
      }
    >
      {tl.loading && <Loading />}
      <ErrorBox error={tl.error} onRetry={tl.reload} />
      {tl.data && <Timeline events={tl.data.timeline} />}
    </Card>
  );
}
