"""
Role-based access control with organization isolation.

Every request that touches organization-owned data resolves the organization
first, then requires the user's membership role in it:

    safe methods  → view.rbac_read_role  (default VIEWER)
    other methods → view.rbac_write_role (default EXPERIMENT_MANAGER)

Non-members get 404 (the resource's existence is not revealed); members with an
insufficient role get 403. Views resolve the organization via
get_rbac_organization_id() or an ``experiment_id`` URL kwarg. List endpoints
without a single organization are filtered with accessible_organization_ids().
"""

from rest_framework.exceptions import NotFound
from rest_framework.permissions import SAFE_METHODS, BasePermission

from apps.organizations.models import Membership, Role

NO_ORGANIZATION = object()


def accessible_organization_ids(user):
    if not user or not user.is_authenticated:
        return []
    return list(Membership.objects.filter(user=user).values_list("organization_id", flat=True))


def get_membership(user, organization_id):
    if not user or not user.is_authenticated or organization_id is None:
        return None
    return Membership.objects.filter(user=user, organization_id=organization_id).first()


def has_org_role(user, organization_id, role):
    if getattr(user, "is_superuser", False):
        return True
    membership = get_membership(user, organization_id)
    return bool(membership and membership.has_role(role))


def experiment_organization_id(experiment_id):
    from apps.experiments.models import Experiment

    return (
        Experiment.objects.filter(id=experiment_id)
        .values_list("project__organization_id", flat=True)
        .first()
    )


def project_organization_id(project_id):
    from apps.organizations.models import Project

    return Project.objects.filter(id=project_id).values_list("organization_id", flat=True).first()


def required_role(request, view):
    if request.method in SAFE_METHODS:
        return getattr(view, "rbac_read_role", Role.VIEWER)
    return getattr(view, "rbac_write_role", Role.EXPERIMENT_MANAGER)


class OrganizationRolePermission(BasePermission):
    """Default permission for dashboard (JWT) endpoints."""

    message = "Your role in this organization does not allow this action."

    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return False
        if user.is_superuser:
            return True

        organization_id = self._organization_id(request, view)
        if organization_id is NO_ORGANIZATION:
            return True
        if organization_id is None:
            # The referenced resource does not exist; let the view return its own 404/400.
            return True

        membership = get_membership(user, organization_id)
        if membership is None:
            raise NotFound()
        return membership.has_role(required_role(request, view))

    @staticmethod
    def _organization_id(request, view):
        resolver = getattr(view, "get_rbac_organization_id", None)
        if resolver is not None:
            return resolver()
        experiment_id = getattr(view, "kwargs", {}).get("experiment_id")
        if experiment_id is not None:
            return experiment_organization_id(experiment_id)
        return NO_ORGANIZATION
