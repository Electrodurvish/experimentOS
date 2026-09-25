from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.views import TokenObtainPairView

from apps.accounts.models import APIKey
from apps.accounts.serializers import (
    APIKeyCreateSerializer,
    APIKeyResponseSerializer,
    RegisterSerializer,
    UserSerializer,
)
from apps.audit.models import AuditAction
from apps.audit.service import record_audit
from apps.common.throttling import AuthRateThrottle
from apps.organizations.models import Project, Role
from apps.organizations.permissions import has_org_role


class RegisterView(generics.CreateAPIView):
    serializer_class = RegisterSerializer
    permission_classes = [permissions.AllowAny]
    throttle_classes = [AuthRateThrottle]


class ThrottledTokenObtainPairView(TokenObtainPairView):
    throttle_classes = [AuthRateThrottle]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        return Response(
            UserSerializer(user).data,
            status=status.HTTP_201_CREATED,
        )


class MeView(generics.RetrieveAPIView):
    serializer_class = UserSerializer

    def get_object(self):
        return self.request.user


class APIKeyCreateView(APIView):

    def post(self, request):
        serializer = APIKeyCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        project_id = serializer.validated_data["project_id"]
        try:
            project = Project.objects.get(id=project_id)
        except Project.DoesNotExist:
            return Response(
                {"detail": "Project not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        if not has_org_role(request.user, project.organization_id, Role.ADMIN):
            return Response(
                {"detail": "Creating API keys requires the ADMIN role."},
                status=status.HTTP_403_FORBIDDEN,
            )

        environment = serializer.validated_data.get("environment", "live")
        raw_key, prefix, hashed = APIKey.generate_key(environment)

        api_key = APIKey.objects.create(
            key_prefix=prefix,
            hashed_key=hashed,
            name=serializer.validated_data["name"],
            project=project,
            created_by=request.user,
        )

        record_audit(
            AuditAction.API_KEY_CREATED,
            organization=project.organization,
            actor=request.user,
            new_value={"name": api_key.name, "project": str(project.id), "prefix": prefix},
        )

        response_data = APIKeyResponseSerializer(api_key).data
        response_data["key"] = raw_key
        return Response(response_data, status=status.HTTP_201_CREATED)

    def get(self, request):
        keys = APIKey.objects.filter(created_by=request.user, is_active=True)
        serializer = APIKeyResponseSerializer(keys, many=True)
        return Response(serializer.data)


class APIKeyRevokeView(APIView):
    """
    DELETE /api/v1/auth/api-keys/{id}/  Revoke an API key (ADMIN of its organization).
    """

    def delete(self, request, key_id):
        api_key = APIKey.objects.select_related("project__organization").filter(id=key_id).first()
        if api_key is None or not has_org_role(request.user, api_key.project.organization_id, Role.VIEWER):
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        if not has_org_role(request.user, api_key.project.organization_id, Role.ADMIN):
            return Response({"detail": "Revoking API keys requires the ADMIN role."},
                            status=status.HTTP_403_FORBIDDEN)
        api_key.is_active = False
        api_key.save(update_fields=["is_active", "updated_at"])
        record_audit(
            AuditAction.API_KEY_REVOKED,
            organization=api_key.project.organization,
            actor=request.user,
            old_value={"name": api_key.name, "prefix": api_key.key_prefix},
        )
        return Response(status=status.HTTP_204_NO_CONTENT)
