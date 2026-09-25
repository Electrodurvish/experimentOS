import { useState } from 'react';
import { audit, type Experiment } from '../../api';
import { AuditTable } from '../../components/AuditTable';
import { Card, Empty, ErrorBox, Loading, Pagination } from '../../components/ui';
import { useAsync } from '../../lib/useAsync';

export function AuditTab({ experiment }: { experiment: Experiment }) {
  const [page, setPage] = useState(1);
  const logs = useAsync(() => audit.list({ experiment: experiment.id, page }), `audit-${experiment.id}-${page}`);
  return (
    <Card title="Audit log">
      {logs.loading && <Loading />}
      <ErrorBox error={logs.error} onRetry={logs.reload} />
      {logs.data && logs.data.results.length === 0 && <Empty>No audit entries.</Empty>}
      {logs.data && <AuditTable logs={logs.data.results} />}
      {logs.data && <Pagination page={page} count={logs.data.count} onPage={setPage} />}
    </Card>
  );
}
