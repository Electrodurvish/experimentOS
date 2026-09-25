from rest_framework import serializers

from apps.experiments.models import (
    Experiment,
    ExperimentStatus,
    ExperimentVersion,
    TargetingRule,
    Variant,
)
from apps.experiments.validators import validate_variant_buckets


class VariantSerializer(serializers.ModelSerializer):
    class Meta:
        model = Variant
        fields = [
            "id", "key", "name", "description", "is_control",
            "traffic_percentage", "bucket_start", "bucket_end", "payload",
        ]
        read_only_fields = ["id"]


class TargetingRuleSerializer(serializers.ModelSerializer):
    class Meta:
        model = TargetingRule
        fields = ["id", "rules_json"]
        read_only_fields = ["id"]


class ExperimentVersionSerializer(serializers.ModelSerializer):
    variants = VariantSerializer(many=True, read_only=True)
    targeting = TargetingRuleSerializer(read_only=True)

    class Meta:
        model = ExperimentVersion
        fields = [
            "id", "version_number", "traffic_allocation",
            "is_active", "is_locked", "variants", "targeting", "created_at",
        ]
        read_only_fields = ["id", "version_number", "is_active", "is_locked", "created_at"]


class ExperimentListSerializer(serializers.ModelSerializer):
    current_version = ExperimentVersionSerializer(read_only=True)
    allowed_transitions = serializers.SerializerMethodField()

    class Meta:
        model = Experiment
        fields = [
            "id", "key", "name", "description", "hypothesis",
            "experiment_type", "status", "owner", "current_version",
            "rollout_percentage", "started_at", "ended_at", "allowed_transitions",
            "created_at", "updated_at",
        ]
        read_only_fields = [
            "id", "status", "current_version", "rollout_percentage", "started_at", "ended_at",
            "allowed_transitions", "created_at", "updated_at",
        ]

    def get_allowed_transitions(self, obj):
        from apps.experiments.state_machine import ExperimentStateMachine
        sm = ExperimentStateMachine(obj)
        return [s.value for s in sm.get_allowed_transitions()]


class ExperimentCreateSerializer(serializers.ModelSerializer):
    project_id = serializers.UUIDField()

    class Meta:
        model = Experiment
        fields = ["id", "project_id", "key", "name", "description", "hypothesis", "experiment_type"]
        read_only_fields = ["id"]


class TransitionSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=ExperimentStatus.choices)


class VersionCreateSerializer(serializers.Serializer):
    traffic_allocation = serializers.IntegerField(min_value=0, max_value=10000, default=10000)
    variants = VariantSerializer(many=True)
    targeting = TargetingRuleSerializer(required=False)

    def validate(self, data):
        validate_variant_buckets(
            [dict(v) for v in data["variants"]],
            data.get("traffic_allocation", 10000),
        )
        return data
