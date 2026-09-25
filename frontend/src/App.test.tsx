import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { App } from './App';
import { AuthProvider } from './auth/AuthProvider';

function json(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } });
}

describe('App', () => {
  afterEach(() => vi.restoreAllMocks());

  it('redirects anonymous users to the login page', () => {
    render(
      <MemoryRouter initialEntries={['/experiments']} future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <AuthProvider>
          <App />
        </AuthProvider>
      </MemoryRouter>,
    );
    expect(screen.getByRole('button', { name: 'Sign in' })).toBeInTheDocument();
  });

  it('signs in, loads the user and shows the dashboard', async () => {
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
      const url = String(input);
      if (url.endsWith('/auth/token/')) return json(200, { access: 'a', refresh: 'r' });
      if (url.endsWith('/auth/me/')) {
        return json(200, { id: 'u', email: 'viewer@example.com', memberships: [{ organization_id: 'o', organization_name: 'Acme', role: 'VIEWER' }] });
      }
      if (url.includes('/experiments/')) return json(200, { count: 0, next: null, previous: null, results: [] });
      return json(404, { detail: 'Not found.' });
    });
    render(
      <MemoryRouter initialEntries={['/login']} future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <AuthProvider>
          <App />
        </AuthProvider>
      </MemoryRouter>,
    );
    await userEvent.type(screen.getByLabelText('Email'), 'viewer@example.com');
    await userEvent.type(screen.getByLabelText('Password'), 'secret123');
    await userEvent.click(screen.getByRole('button', { name: 'Sign in' }));

    expect(await screen.findByRole('heading', { name: 'Dashboard' })).toBeInTheDocument();
    expect(screen.getByText('Read-only')).toBeInTheDocument();
    expect(await screen.findByText(/No running or paused experiments/)).toBeInTheDocument();
  });
});
