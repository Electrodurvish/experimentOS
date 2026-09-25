from django.contrib.auth import get_user_model
from django.utils.text import slugify
from rest_framework import serializers

from apps.organizations.models import Membership, Organization, Project


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


class MembershipSerializer(serializers.ModelSerializer):
    email = serializers.EmailField(write_only=True, required=False)
    user_email = serializers.EmailField(source="user.email", read_only=True)

    class Meta:
        model = Membership
        fields = ["id", "email", "user", "user_email", "role", "created_at"]
        read_only_fields = ["id", "user", "user_email", "created_at"]

    def validate(self, data):
        if self.instance is None:
            email = data.pop("email", None)
            if not email:
                raise serializers.ValidationError({"email": "This field is required."})
            user = get_user_model().objects.filter(email__iexact=email).first()
            if user is None:
                raise serializers.ValidationError({"email": "No user with this email."})
            org_id = self.context["view"].kwargs["organization_pk"]
            if Membership.objects.filter(organization_id=org_id, user=user).exists():
                raise serializers.ValidationError({"email": "User is already a member."})
            data["user"] = user
        else:
            data.pop("email", None)
        return data
