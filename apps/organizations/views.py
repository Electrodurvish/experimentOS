from django.contrib.auth import get_user_model
from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework import mixins, viewsets
from rest_framework.exceptions import ValidationError

from apps.audit.models import AuditAction
from apps.audit.service import record_audit
from apps.organizations.models import Membership, Organization, Project, Role
from apps.organizations.permissions import (
    NO_ORGANIZATION,
    accessible_organization_ids,
    project_organization_id,
)
from apps.organizations.serializers import MembershipSerializer, OrganizationSerializer, ProjectSerializer

User = get_user_model()


class OrganizationViewSet(viewsets.ModelViewSet):
    serializer_class = OrganizationSerializer
    filterset_fields = ["name"]
    search_fields = ["name", "slug"]
    ordering_fields = ["name", "created_at"]
    ordering = ["-created_at"]
    rbac_write_role = Role.ADMIN

    def get_queryset(self):
        if self.request.user.is_superuser:
            return Organization.objects.all()
        return Organization.objects.filter(id__in=accessible_organization_ids(self.request.user))

    def get_rbac_organization_id(self):
        # Creating an organization needs no membership; the creator becomes its ADMIN.
        return self.kwargs.get("pk", NO_ORGANIZATION)

    @transaction.atomic
    def perform_create(self, serializer):
        organization = serializer.save()
        Membership.objects.create(organization=organization, user=self.request.user, role=Role.ADMIN)
        record_audit(
            AuditAction.PERMISSION_CHANGED,
            organization=organization,
            actor=self.request.user,
            new_value={"user": self.request.user.email, "role": Role.ADMIN},
            metadata={"reason": "organization created"},
        )


class ProjectViewSet(viewsets.ModelViewSet):
    serializer_class = ProjectSerializer
    filterset_fields = ["organization"]
    search_fields = ["name", "slug"]
    ordering_fields = ["name", "created_at"]
    ordering = ["-created_at"]
    rbac_write_role = Role.ADMIN

    def get_queryset(self):
        queryset = Project.objects.select_related("organization")
        if not self.request.user.is_superuser:
            queryset = queryset.filter(organization_id__in=accessible_organization_ids(self.request.user))
        org_id = self.kwargs.get("organization_pk")
        if org_id:
            queryset = queryset.filter(organization_id=org_id)
        return queryset

    def get_rbac_organization_id(self):
        if "organization_pk" in self.kwargs:
            return self.kwargs["organization_pk"]
        if "pk" in self.kwargs:
            return project_organization_id(self.kwargs["pk"])
        if self.request.method == "POST":
            org_id = self.request.data.get("organization_id") if hasattr(self.request.data, "get") else None
            return org_id or None
        return NO_ORGANIZATION

    def perform_create(self, serializer):
        org_id = self.kwargs.get("organization_pk")
        if org_id:
            serializer.save(organization_id=org_id)
        else:
            serializer.save()


class MembershipViewSet(mixins.ListModelMixin, mixins.CreateModelMixin, mixins.UpdateModelMixin,
                        mixins.DestroyModelMixin, viewsets.GenericViewSet):
    """
    /api/v1/organizations/{organization_pk}/members/
    Viewers can list members; only ADMINs can add, change or remove them.
    """
    serializer_class = MembershipSerializer
    rbac_write_role = Role.ADMIN
    pagination_class = None

    def get_rbac_organization_id(self):
        return self.kwargs["organization_pk"]

    def get_queryset(self):
        return Membership.objects.filter(organization_id=self.kwargs["organization_pk"]).select_related("user")

    def perform_create(self, serializer):
        organization = get_object_or_404(Organization, id=self.kwargs["organization_pk"])
        membership = serializer.save(organization=organization)
        self._audit(membership, None, membership.role)

    def perform_update(self, serializer):
        old_role = serializer.instance.role
        if old_role == Role.ADMIN and serializer.validated_data.get("role", old_role) != Role.ADMIN:
            self._ensure_not_last_admin(serializer.instance)
        membership = serializer.save()
        self._audit(membership, old_role, membership.role)

    def perform_destroy(self, instance):
        if instance.role == Role.ADMIN:
            self._ensure_not_last_admin(instance)
        self._audit(instance, instance.role, None)
        instance.delete()

    @staticmethod
    def _ensure_not_last_admin(membership):
        admins = Membership.objects.filter(organization_id=membership.organization_id, role=Role.ADMIN)
        if admins.exclude(id=membership.id).count() == 0:
            raise ValidationError("An organization must keep at least one ADMIN.")

    def _audit(self, membership, old_role, new_role):
        record_audit(
            AuditAction.PERMISSION_CHANGED,
            organization=membership.organization,
            actor=self.request.user,
            old_value={"user": membership.user.email, "role": old_role} if old_role else None,
            new_value={"user": membership.user.email, "role": new_role} if new_role else None,
        )
