import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { DebuggerPage } from './DebuggerPage';

function json(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } });
}

const config = {
  version_number: 2,
  traffic_allocation: 10000,
  created_at: '2026-09-01T10:00:00Z',
  targeting: null,
  variants: [
    { key: 'control', is_control: true, traffic_percentage: 5000, bucket_start: 0, bucket_end: 4999 },
    { key: 'treatment', is_control: false, traffic_percentage: 5000, bucket_start: 5000, bucket_end: 9999 },
  ],
};

describe('DebuggerPage', () => {
  afterEach(() => vi.restoreAllMocks());

  it('explains a user with a ✓/✗ checklist and the config at assignment', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
      const url = String(input);
      if (url.includes('/users/u42/debug/')) {
        return json(200, {
          user_id: 'u42',
          experiment_key: 'checkout_v3',
          context: {},
          result: { assigned: true, variant_key: 'treatment', variant_payload: {}, bucket: 7342, version_number: 2, reason: 'assigned', source: 'sticky' },
          evaluation_steps: [{ step: 'status_check', passed: true, detail: 'Experiment is RUNNING.' }],
          explanation: ['✓ Experiment is RUNNING.', '✗ Targeting rule country=US did not match.'],
          recorded_assignment: { version_number: 2, variant_key: 'treatment', bucket: 7342, assigned_at: '2026-09-01T11:00:00Z', context: {}, config_at_assignment: config },
          sticky: null,
        });
      }
      if (url.includes('/experiments/')) {
        return json(200, { count: 1, next: null, previous: null, results: [{ id: 'e1', key: 'checkout_v3', status: 'RUNNING' }] });
      }
      return json(404, { detail: 'Not found.' });
    });

    render(
      <MemoryRouter initialEntries={['/debugger?mode=user&experiment=e1&user=u42']} future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <DebuggerPage />
      </MemoryRouter>,
    );
    await screen.findByRole('option', { name: /checkout_v3/ });
    await userEvent.click(screen.getByRole('button', { name: 'Explain assignment' }));

    const checklist = await screen.findByRole('list', { name: 'Explanation' });
    expect(checklist).toHaveTextContent('Experiment is RUNNING.');
    expect(screen.getAllByLabelText('failed')[0]).toHaveTextContent('✗');
    expect(screen.getByText('Config at assignment')).toBeInTheDocument();
    expect(screen.getByText('assigned')).toBeInTheDocument();
    expect(fetchMock.mock.calls.some(([u]) => String(u).includes('/api/v1/experiments/e1/users/u42/debug/'))).toBe(true);
  });
});
