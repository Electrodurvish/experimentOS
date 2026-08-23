from django.contrib.auth import get_user_model
from rest_framework import serializers

from apps.accounts.models import APIKey

User = get_user_model()


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["id", "email", "username", "first_name", "last_name", "created_at"]
        read_only_fields = ["id", "created_at"]


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=8)

    class Meta:
        model = User
        fields = ["id", "email", "username", "password", "first_name", "last_name"]
        read_only_fields = ["id"]

    def create(self, validated_data):
        return User.objects.create_user(**validated_data)


class APIKeyCreateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=255)
    project_id = serializers.UUIDField()
    environment = serializers.ChoiceField(choices=["live", "test"], default="live")


class APIKeyResponseSerializer(serializers.ModelSerializer):
    key = serializers.CharField(read_only=True)

    class Meta:
        model = APIKey
        fields = ["id", "name", "key", "key_prefix", "project", "created_at", "expires_at"]
        read_only_fields = ["id", "key", "key_prefix", "project", "created_at"]
