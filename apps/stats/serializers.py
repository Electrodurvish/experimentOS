from rest_framework import serializers

from apps.stats.models import ExperimentMetric, MetricType


class ExperimentMetricSerializer(serializers.ModelSerializer):
    class Meta:
        model = ExperimentMetric
        fields = ["id", "name", "event_name", "metric_type", "aggregation", "created_at"]
        read_only_fields = ["id", "created_at"]

    def validate(self, data):
        experiment_id = self.context["view"].kwargs["experiment_id"]
        existing = ExperimentMetric.objects.filter(experiment_id=experiment_id)
        if self.instance is not None:
            existing = existing.exclude(id=self.instance.id)
        name = data.get("name", getattr(self.instance, "name", None))
        if existing.filter(name=name).exists():
            raise serializers.ValidationError({"name": "A metric with this name already exists."})
        metric_type = data.get("metric_type", getattr(self.instance, "metric_type", None))
        if metric_type == MetricType.PRIMARY and existing.filter(metric_type=MetricType.PRIMARY).exists():
            raise serializers.ValidationError({"metric_type": "An experiment can have only one PRIMARY metric."})
        return data
