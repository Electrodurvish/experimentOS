from rest_framework import serializers


class EvaluateRequestSerializer(serializers.Serializer):
    user_id = serializers.CharField(max_length=255)
    experiment_keys = serializers.ListField(
        child=serializers.CharField(max_length=255),
        min_length=1,
    )
    context = serializers.DictField(default=dict)


class EvaluationResultSerializer(serializers.Serializer):
    assigned = serializers.BooleanField()
    variant_key = serializers.CharField(allow_null=True)
    variant_payload = serializers.DictField(allow_null=True)
    bucket = serializers.IntegerField(allow_null=True)
    version_number = serializers.IntegerField(allow_null=True)
    reason = serializers.CharField()
    source = serializers.CharField(default="")


class DebugRequestSerializer(serializers.Serializer):
    user_id = serializers.CharField(max_length=255)
    experiment_key = serializers.CharField(max_length=255)
    context = serializers.DictField(default=dict)


class DebugStepSerializer(serializers.Serializer):
    step = serializers.CharField()
    passed = serializers.BooleanField(allow_null=True)
    detail = serializers.CharField()
