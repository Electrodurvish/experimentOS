from rest_framework import serializers

from apps.audit.models import AuditLog


class AuditLogSerializer(serializers.ModelSerializer):
    actor_email = serializers.EmailField(source="actor.email", read_only=True, default=None)

    class Meta:
        model = AuditLog
        fields = [
            "id", "experiment", "organization", "actor", "actor_email", "action",
            "old_value", "new_value", "metadata", "ip_address", "created_at",
        ]
        read_only_fields = fields
