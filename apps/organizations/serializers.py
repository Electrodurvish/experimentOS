from django.utils.text import slugify
from rest_framework import serializers

from apps.organizations.models import Organization, Project


class OrganizationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Organization
        fields = ["id", "name", "slug", "created_at", "updated_at"]
        read_only_fields = ["id", "slug", "created_at", "updated_at"]

    def create(self, validated_data):
        validated_data["slug"] = slugify(validated_data["name"])
        return super().create(validated_data)


class ProjectSerializer(serializers.ModelSerializer):
    organization_id = serializers.UUIDField(write_only=True, required=False)

    class Meta:
        model = Project
        fields = ["id", "organization", "organization_id", "name", "slug", "created_at", "updated_at"]
        read_only_fields = ["id", "organization", "slug", "created_at", "updated_at"]

    def create(self, validated_data):
        if "organization_id" in validated_data:
            validated_data["organization_id"] = validated_data.pop("organization_id")
        validated_data["slug"] = slugify(validated_data["name"])
        return super().create(validated_data)
