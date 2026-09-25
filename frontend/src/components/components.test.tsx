import { render, screen, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { ApiError, type Experiment, type ExperimentResults } from '../api';
import { AuthContext, type AuthValue } from '../auth/context';
import { ChecksList, EvidenceList } from './Evidence';
import { ExperimentHeader } from './ExperimentHeader';
import { Timeline } from './Timeline';
import { ErrorBox } from './ui';

function withAuth(ui: React.ReactNode, canEdit = true) {
  const value: AuthValue = { user: { id: 'u', email: 'a@b.c' }, status: 'authenticated', login: async () => {}, logout: () => {}, canEdit };
  return (
    <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <AuthContext.Provider value={value}>{ui}</AuthContext.Provider>
    </MemoryRouter>
  );
}

const experiment: Experiment = {
  id: 'e1',
  key: 'checkout_v3',
  name: 'Checkout v3',
  description: '',
  hypothesis: '',
  experiment_type: 'AB',
  status: 'RUNNING',
  owner: null,
  current_version: null,
  rollout_percentage: 5000,
  started_at: null,
  ended_at: null,
  allowed_transitions: ['PAUSED', 'COMPLETED'],
  created_at: '',
  updated_at: '',
};

const results: ExperimentResults = {
  experiment_id: 'e1',
  experiment_key: 'checkout_v3',
  srm: null,
  recommended_sample_size_per_variant: 0,
  variants: {
    control: { exposures: 0, unique_users: 1000, conversions: 101, conversion_rate: 0.101, ci_lower: 0, ci_upper: 0 },
    treatment: { exposures: 0, unique_users: 1000, conversions: 124, conversion_rate: 0.124, ci_lower: 0, ci_upper: 0, lift: 0.228, is_significant: true },
  },
};

describe('ExperimentHeader', () => {
  it('renders the overview card like the plan mockup', () => {
    render(withAuth(<ExperimentHeader experiment={experiment} results={results} healthScore={82} />));
    expect(screen.getByRole('heading', { name: 'checkout_v3' })).toBeInTheDocument();
    expect(screen.getByText('RUNNING')).toBeInTheDocument();
    expect(screen.getByText('50%')).toBeInTheDocument();
    expect(screen.getByText('82/100')).toBeInTheDocument();
    expect(screen.getByText('10.1%')).toBeInTheDocument();
    expect(screen.getByText('12.4%')).toBeInTheDocument();
    expect(screen.getByText('+22.8%')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Pause' })).toBeInTheDocument();
  });

  it('hides lifecycle controls for read-only roles', () => {
    render(withAuth(<ExperimentHeader experiment={experiment} results={results} />, false));
    expect(screen.queryByRole('button', { name: 'Pause' })).not.toBeInTheDocument();
  });
});

describe('Evidence and checks', () => {
  it('numbers evidence and marks cited items', () => {
    render(
      <EvidenceList
        evidence={[
          { id: 'E1', kind: 'guardrail', statement: 'Error rate breached' },
          { id: 'E2', kind: 'lift', statement: 'Lift not significant' },
        ]}
        cited={['E2']}
      />,
    );
    const items = screen.getAllByRole('listitem');
    expect(items).toHaveLength(2);
    expect(within(items[0]!).getByText('E1')).toBeInTheDocument();
    expect(items[1]).toHaveClass('cited');
  });

  it('shows ✓ and ✗ for checks', () => {
    render(
      <ChecksList
        checks={[
          { name: 'health', label: 'Health score', passed: true, detail: '82 ≥ 70' },
          { name: 'guardrails', label: 'Guardrails', passed: false, detail: '1 breached' },
        ]}
      />,
    );
    expect(screen.getByLabelText('passed')).toHaveTextContent('✓');
    expect(screen.getByLabelText('failed')).toHaveTextContent('✗');
  });
});

describe('Timeline', () => {
  it('lists events chronologically', () => {
    render(
      <Timeline
        events={[
          { event_type: 'rollback_triggered', title: 'Automatic rollback → 10%', detail: '', metadata: {}, created_at: '2026-09-01T13:31:00Z' },
          { event_type: 'experiment_started', title: 'Experiment started', detail: '', metadata: {}, created_at: '2026-09-01T10:00:00Z' },
        ]}
      />,
    );
    const titles = [...document.querySelectorAll('.timeline-title')].map((n) => n.textContent);
    expect(titles).toEqual(['Experiment started', 'Automatic rollback → 10%']);
  });
});

describe('ErrorBox', () => {
  it('shows a friendly message when a new endpoint 404s', () => {
    render(<ErrorBox error={new ApiError(404, { detail: 'Not found.' })} feature="Explain" />);
    expect(screen.getByText(/Explain isn’t available yet/)).toBeInTheDocument();
  });
});
