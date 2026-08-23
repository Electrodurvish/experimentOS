from rest_framework import serializers


class TrackEventSerializer(serializers.Serializer):
    event_id = serializers.CharField(max_length=255, required=False)
    user_id = serializers.CharField(max_length=255)
    event_name = serializers.CharField(max_length=255)
    value = serializers.FloatField(default=0.0)
    metadata = serializers.DictField(default=dict)
    timestamp = serializers.DateTimeField(required=False)


class VariantResultSerializer(serializers.Serializer):
    exposures = serializers.IntegerField()
    unique_users = serializers.IntegerField()
    conversions = serializers.IntegerField()
    conversion_rate = serializers.FloatField()
