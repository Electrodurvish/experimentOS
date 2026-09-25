from rest_framework import serializers

from apps.decisions.models import Decision, Guardrail, RolloutChange, RolloutPolicy


class GuardrailSerializer(serializers.ModelSerializer):
    class Meta:
        model = Guardrail
        fields = [
            "id", "name", "metric_name", "source", "operator", "threshold",
            "action", "is_active", "created_at", "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


class RolloutPolicySerializer(serializers.ModelSerializer):
    class Meta:
        model = RolloutPolicy
        fields = [
            "stages", "auto_advance", "auto_rollback", "rollback_percentage",
            "min_health_score", "min_stage_duration_minutes", "min_confidence", "updated_at",
        ]
        read_only_fields = ["updated_at"]

    def validate_stages(self, stages):
        if not stages or not all(isinstance(s, int) and 0 < s <= 10000 for s in stages):
            raise serializers.ValidationError("Stages must be integers in (0, 10000].")
        if stages != sorted(set(stages)):
            raise serializers.ValidationError("Stages must be strictly ascending.")
        return stages


class DecisionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Decision
        fields = [
            "id", "recommendation", "confidence", "confidence_label", "summary",
            "evidence", "checks", "inputs", "applied_action", "from_percentage",
            "to_percentage", "triggered_by", "actor", "created_at",
        ]
        read_only_fields = fields


class RolloutChangeSerializer(serializers.ModelSerializer):
    class Meta:
        model = RolloutChange
        fields = [
            "id", "action", "from_percentage", "to_percentage", "reason",
            "automated", "decision", "actor", "created_at",
        ]
        read_only_fields = fields


class RolloutUpdateSerializer(serializers.Serializer):
    percentage = serializers.IntegerField(min_value=0, max_value=10000)
    reason = serializers.CharField(max_length=255)


class RollbackSerializer(serializers.Serializer):
    to_percentage = serializers.IntegerField(min_value=0, max_value=10000, required=False)
    reason = serializers.CharField(max_length=255, default="Manual rollback")


class DecisionRequestSerializer(serializers.Serializer):
    apply = serializers.BooleanField(default=False)
    segments = serializers.ListField(child=serializers.DictField(), required=False, default=list)
    interactions = serializers.ListField(child=serializers.DictField(), required=False, default=list)
