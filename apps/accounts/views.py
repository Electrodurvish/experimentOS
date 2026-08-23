from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import APIKey
from apps.accounts.serializers import (
    APIKeyCreateSerializer,
    APIKeyResponseSerializer,
    RegisterSerializer,
    UserSerializer,
)
from apps.organizations.models import Project


class RegisterView(generics.CreateAPIView):
    serializer_class = RegisterSerializer
    permission_classes = [permissions.AllowAny]

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
    permission_classes = [permissions.IsAuthenticated]

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

        environment = serializer.validated_data.get("environment", "live")
        raw_key, prefix, hashed = APIKey.generate_key(environment)

        api_key = APIKey.objects.create(
            key_prefix=prefix,
            hashed_key=hashed,
            name=serializer.validated_data["name"],
            project=project,
            created_by=request.user,
        )

        response_data = APIKeyResponseSerializer(api_key).data
        response_data["key"] = raw_key
        return Response(response_data, status=status.HTTP_201_CREATED)

    def get(self, request):
        keys = APIKey.objects.filter(created_by=request.user, is_active=True)
        serializer = APIKeyResponseSerializer(keys, many=True)
        return Response(serializer.data)
