from django.urls import include, path
from rest_framework.routers import DefaultRouter

from apps.organizations.views import OrganizationViewSet, ProjectViewSet

router = DefaultRouter()
router.register("organizations", OrganizationViewSet, basename="organization")
router.register("projects", ProjectViewSet, basename="project")

# Nested project routes under organizations
org_project_router = DefaultRouter()
org_project_router.register("projects", ProjectViewSet, basename="org-project")

urlpatterns = [
    path("", include(router.urls)),
    path("organizations/<uuid:organization_pk>/", include(org_project_router.urls)),
]
