import type { Role, User } from '../api/types';

export const MUTATING_ROLES: Role[] = ['ADMIN', 'EXPERIMENT_MANAGER'];

/**
 * Whether the user may perform mutating actions. If the backend reports no
 * memberships (older API, or a superuser without memberships), everything is
 * allowed; the backend remains the authority.
 * With an organization id, only that organization's role counts (no membership →
 * read-only). Without one (org-agnostic pages), the strongest role decides.
 */
export function canMutate(user: User | null | undefined, organizationId?: string | null): boolean {
  const memberships = user?.memberships;
  if (!memberships || memberships.length === 0) return true;
  if (organizationId) {
    const m = memberships.find((x) => x.organization_id === organizationId);
    return !!m && MUTATING_ROLES.includes(m.role);
  }
  return memberships.some((m) => MUTATING_ROLES.includes(m.role));
}

export function roleFor(user: User | null | undefined, organizationId?: string | null): Role | null {
  if (!organizationId) return null;
  return user?.memberships?.find((m) => m.organization_id === organizationId)?.role ?? null;
}

export function primaryRole(user: User | null | undefined): Role | null {
  const ms = user?.memberships;
  if (!ms || ms.length === 0) return null;
  const order: Role[] = ['ADMIN', 'EXPERIMENT_MANAGER', 'ANALYST', 'VIEWER'];
  return order.find((r) => ms.some((m) => m.role === r)) ?? null;
}
