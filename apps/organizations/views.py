from rest_framework import viewsets

from apps.organizations.models import Organization, Project
from apps.organizations.serializers import OrganizationSerializer, ProjectSerializer


class OrganizationViewSet(viewsets.ModelViewSet):
    queryset = Organization.objects.all()
    serializer_class = OrganizationSerializer
    filterset_fields = ["name"]
    search_fields = ["name", "slug"]
    ordering_fields = ["name", "created_at"]
    ordering = ["-created_at"]


class ProjectViewSet(viewsets.ModelViewSet):
    serializer_class = ProjectSerializer
    filterset_fields = ["organization"]
    search_fields = ["name", "slug"]
    ordering_fields = ["name", "created_at"]
    ordering = ["-created_at"]

    def get_queryset(self):
        queryset = Project.objects.select_related("organization").all()
        org_id = self.kwargs.get("organization_pk")
        if org_id:
            queryset = queryset.filter(organization_id=org_id)
        return queryset

    def perform_create(self, serializer):
        org_id = self.kwargs.get("organization_pk")
        if org_id:
            serializer.save(organization_id=org_id)
        else:
            serializer.save()
