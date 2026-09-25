import type { Role, User } from '../api/types';

export const MUTATING_ROLES: Role[] = ['ADMIN', 'EXPERIMENT_MANAGER'];

/**
 * Whether the user may perform mutating actions. If the backend does not report
 * memberships yet, everything is allowed (the backend remains the authority).
 * With an organization id, that organization's role decides; otherwise the user's
 * strongest role across organizations does.
 */
export function canMutate(user: User | null | undefined, organizationId?: string | null): boolean {
  const memberships = user?.memberships;
  if (!memberships || memberships.length === 0) return true;
  if (organizationId) {
    const m = memberships.find((x) => x.organization_id === organizationId);
    if (m) return MUTATING_ROLES.includes(m.role);
  }
  return memberships.some((m) => MUTATING_ROLES.includes(m.role));
}

export function primaryRole(user: User | null | undefined): Role | null {
  const ms = user?.memberships;
  if (!ms || ms.length === 0) return null;
  const order: Role[] = ['ADMIN', 'EXPERIMENT_MANAGER', 'ANALYST', 'VIEWER'];
  return order.find((r) => ms.some((m) => m.role === r)) ?? null;
}
