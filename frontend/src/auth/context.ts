import { createContext, useContext } from 'react';
import type { User } from '../api';

export interface AuthValue {
  user: User | null;
  status: 'loading' | 'authenticated' | 'anonymous';
  login: (email: string, password: string) => Promise<void>;
  logout: () => void;
  /** Whether the user may mutate anything at all (strongest role across orgs). */
  canEdit: boolean;
  /** Whether the user may mutate resources of this organization (its own role). */
  canEditOrg: (organizationId?: string | null) => boolean;
}

export const AuthContext = createContext<AuthValue | null>(null);

export function useAuth(): AuthValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used inside <AuthProvider>');
  return ctx;
}

/** Editable for this experiment/resource's organization; falls back to the global flag when the org is unknown. */
export function useCanEdit(organizationId?: string | null): boolean {
  const { canEdit, canEditOrg } = useAuth();
  return organizationId ? canEditOrg(organizationId) : canEdit;
}
