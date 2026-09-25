import { Navigate, Route, Routes } from 'react-router-dom';
import { Layout } from './components/Layout';
import { RequireAuth } from './components/RequireAuth';
import { AIQueryPage } from './pages/AIQueryPage';
import { AlertsPage } from './pages/AlertsPage';
import { AuditLogsPage } from './pages/AuditLogsPage';
import { DashboardPage } from './pages/DashboardPage';
import { DebuggerPage } from './pages/DebuggerPage';
import { ExperimentCreatePage } from './pages/ExperimentCreatePage';
import { ExperimentDetailPage } from './pages/ExperimentDetailPage';
import { ExperimentsPage } from './pages/ExperimentsPage';
import { InteractionsPage } from './pages/InteractionsPage';
import { LoginPage } from './pages/LoginPage';
import { RolloutPage } from './pages/RolloutPage';
import { SystemPage } from './pages/SystemPage';
import { VersionEditorPage } from './pages/VersionEditorPage';

export function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route
        element={
          <RequireAuth>
            <Layout />
          </RequireAuth>
        }
      >
        <Route index element={<DashboardPage />} />
        <Route path="experiments" element={<ExperimentsPage />} />
        <Route path="experiments/new" element={<ExperimentCreatePage />} />
        <Route path="experiments/:id" element={<ExperimentDetailPage />} />
        <Route path="experiments/:id/versions/new" element={<VersionEditorPage />} />
        <Route path="rollout" element={<RolloutPage />} />
        <Route path="alerts" element={<AlertsPage />} />
        <Route path="debugger" element={<DebuggerPage />} />
        <Route path="interactions" element={<InteractionsPage />} />
        <Route path="audit" element={<AuditLogsPage />} />
        <Route path="ai" element={<AIQueryPage />} />
        <Route path="system" element={<SystemPage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  );
}
