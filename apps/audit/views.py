from rest_framework import viewsets

from apps.audit.models import AuditLog
from apps.audit.serializers import AuditLogSerializer
from apps.organizations.permissions import NO_ORGANIZATION, accessible_organization_ids


class AuditLogViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = AuditLogSerializer
    filterset_fields = ["experiment", "organization", "action", "actor"]
    ordering = ["-created_at"]

    def get_rbac_organization_id(self):
        return NO_ORGANIZATION  # scoped by queryset below

    def get_queryset(self):
        queryset = AuditLog.objects.select_related("actor", "experiment")
        if self.request.user.is_superuser:
            return queryset.all()
        return queryset.filter(organization_id__in=accessible_organization_ids(self.request.user))
