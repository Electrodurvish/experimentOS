from rest_framework import serializers


class TelemetryIngestSerializer(serializers.Serializer):
    experiment_id = serializers.UUIDField()
    variant_key = serializers.CharField()
    metric_name = serializers.CharField()
    metric_value = serializers.FloatField()
    event_time = serializers.CharField(required=False, allow_null=True)


class TelemetryBatchSerializer(serializers.Serializer):
    data_points = TelemetryIngestSerializer(many=True)
