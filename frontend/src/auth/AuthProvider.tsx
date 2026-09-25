import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react';
import { ApiError, auth, LOGOUT_EVENT, type User } from '../api';
import { canMutate } from '../lib/roles';
import { AuthContext, type AuthValue } from './context';

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [status, setStatus] = useState<AuthValue['status']>(auth.isLoggedIn() ? 'loading' : 'anonymous');

  const loadMe = useCallback(async () => {
    try {
      const me = await auth.me();
      setUser(me);
      setStatus('authenticated');
    } catch (err) {
      if (err instanceof ApiError && (err.status === 401 || err.status === 403)) {
        auth.logout();
        setUser(null);
        setStatus('anonymous');
      } else {
        // Backend unreachable: keep the session; pages will surface request errors.
        setStatus('authenticated');
      }
    }
  }, []);

  useEffect(() => {
    if (auth.isLoggedIn()) void loadMe();
    const onLogout = () => {
      setUser(null);
      setStatus('anonymous');
    };
    window.addEventListener(LOGOUT_EVENT, onLogout);
    return () => window.removeEventListener(LOGOUT_EVENT, onLogout);
  }, [loadMe]);

  const login = useCallback(
    async (email: string, password: string) => {
      await auth.login(email, password);
      await loadMe();
    },
    [loadMe],
  );

  const logout = useCallback(() => {
    auth.logout();
    setUser(null);
    setStatus('anonymous');
  }, []);

  const value = useMemo<AuthValue>(
    () => ({ user, status, login, logout, canEdit: canMutate(user) }),
    [user, status, login, logout],
  );
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
