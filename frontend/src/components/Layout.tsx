import { useEffect, useState } from 'react';
import { NavLink, Outlet, useLocation } from 'react-router-dom';
import { useAuth } from '../auth/context';
import { primaryRole } from '../lib/roles';

const NAV: { to: string; label: string; end?: boolean }[] = [
  { to: '/', label: 'Dashboard', end: true },
  { to: '/experiments', label: 'Experiments' },
  { to: '/rollout', label: 'Rollout Control' },
  { to: '/alerts', label: 'Alerts' },
  { to: '/debugger', label: 'Assignment Debugger' },
  { to: '/interactions', label: 'Interactions' },
  { to: '/audit', label: 'Audit Logs' },
  { to: '/ai', label: 'Ask AI' },
  { to: '/system', label: 'System' },
];

export function Layout() {
  const { user, logout, canEdit } = useAuth();
  const [open, setOpen] = useState(false);
  const location = useLocation();
  useEffect(() => setOpen(false), [location.pathname]);
  const role = primaryRole(user);

  return (
    <div className="app">
      <header className="topbar">
        <button
          type="button"
          className="btn btn-ghost menu-toggle"
          aria-label="Toggle navigation"
          aria-expanded={open}
          onClick={() => setOpen((o) => !o)}
        >
          ☰
        </button>
        <NavLink to="/" className="brand">
          <img src="/favicon.svg" alt="" width={22} height={22} />
          ExperimentOS
        </NavLink>
        <div className="topbar-user">
          {user && <span className="muted small user-email">{user.email}</span>}
          {role && <span className="badge badge-neutral">{role.replace('_', ' ')}</span>}
          {!canEdit && <span className="badge badge-info" title="Mutating controls are hidden">Read-only</span>}
          <button type="button" className="btn btn-small" onClick={logout}>
            Sign out
          </button>
        </div>
      </header>
      <div className="shell">
        <nav className={`sidebar ${open ? 'open' : ''}`} aria-label="Main">
          {NAV.map((n) => (
            <NavLink key={n.to} to={n.to} end={n.end} className={({ isActive }) => (isActive ? 'active' : undefined)}>
              {n.label}
            </NavLink>
          ))}
        </nav>
        <main className="main">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
