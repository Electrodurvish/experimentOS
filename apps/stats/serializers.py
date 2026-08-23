from rest_framework import serializers

from apps.stats.models import ExperimentMetric, MetricType


class ExperimentMetricSerializer(serializers.ModelSerializer):
    class Meta:
        model = ExperimentMetric
        fields = ["id", "name", "event_name", "metric_type"]
        read_only_fields = ["id"]
