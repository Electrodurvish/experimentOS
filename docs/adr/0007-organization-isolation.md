# ADR 0007: Organization isolation through a default permission class

**Status:** Accepted

## Decision
Organizations are the tenancy boundary. `OrganizationRolePermission` is in DRF's
`DEFAULT_PERMISSION_CLASSES`; each view either exposes `get_rbac_organization_id()` or has an
`experiment_id` URL kwarg, and list views filter by `accessible_organization_ids()`.
Non-members receive 404 so resource existence is not leaked; insufficient roles receive 403.

## Consequences
New views are protected by default. Views that intentionally span organizations must opt out by
returning `NO_ORGANIZATION` and filter their querysets themselves (audit logs, AI portfolio query,
debugger lookup by key). SDK endpoints authenticate with a project API key and are scoped to that
project instead.
