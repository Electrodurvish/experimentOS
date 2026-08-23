from rest_framework import serializers

from apps.intelligence.models import TimelineEvent


class TimelineEventSerializer(serializers.ModelSerializer):
    class Meta:
        model = TimelineEvent
        fields = ["id", "event_type", "title", "detail", "metadata", "created_at"]
        read_only_fields = fields


class HealthDimensionSerializer(serializers.Serializer):
    score = serializers.IntegerField()
    detail = serializers.CharField()


class HealthScoreSerializer(serializers.Serializer):
    overall_score = serializers.IntegerField()
    dimensions = serializers.DictField(child=HealthDimensionSerializer())


class SegmentResultSerializer(serializers.Serializer):
    dimension = serializers.CharField()
    value = serializers.CharField()
    control_users = serializers.IntegerField()
    control_rate = serializers.FloatField()
    treatment_users = serializers.IntegerField()
    treatment_rate = serializers.FloatField()
    lift = serializers.FloatField()
    p_value = serializers.FloatField()
    is_significant = serializers.BooleanField()
    has_paradox = serializers.BooleanField()
    contribution_pct = serializers.FloatField()
