import pytest
from rest_framework import serializers
from rest_framework.test import APIClient

from apps.accounts.models import APIKey
from apps.audit.models import AuditAction, AuditLog
from apps.experiments.validators import validate_targeting_rules
from apps.organizations.models import Role


class TestTargetingValidation:
    def test_valid_rules(self):
        validate_targeting_rules({})
        validate_targeting_rules({"operator": "AND", "conditions": [
            {"field": "user.country", "operator": "in", "value": ["IN", "US"]},
            {"operator": "NOT", "conditions": [{"field": "device", "operator": "regex", "value": "^android-[0-9]+$"}]},
        ]})

    @pytest.mark.parametrize("rule", [
        {"field": "x", "operator": "startswith", "value": "a"},
        {"operator": "XOR", "conditions": []},
        {"operator": "NOT", "conditions": [{}, {}]},
        {"field": "x", "operator": "regex", "value": "(a+)+$"},
        {"field": "x", "operator": "regex", "value": "a" * 500},
        {"field": "x", "operator": "regex", "value": "(unclosed"},
        {"operator": "AND", "conditions": "nope"},
    ])
    def test_rejected(self, rule):
        with pytest.raises(serializers.ValidationError):
            validate_targeting_rules(rule)

    def test_depth_limit(self):
        rule = {"field": "x", "operator": "equals", "value": 1}
        for _ in range(12):
            rule = {"operator": "AND", "conditions": [rule]}
        with pytest.raises(serializers.ValidationError):
            validate_targeting_rules(rule)


@pytest.mark.django_db
class TestVersionTargetingEndpoint:
    def test_bad_regex_rejected_at_api(self, authenticated_client, running_experiment):
        payload = {
            "traffic_allocation": 10000,
            "variants": [
                {"key": "control", "name": "C", "is_control": True, "traffic_percentage": 5000,
                 "bucket_start": 0, "bucket_end": 4999},
                {"key": "t", "name": "T", "traffic_percentage": 5000, "bucket_start": 5000, "bucket_end": 9999},
            ],
            "targeting": {"rules_json": {"field": "x", "operator": "regex", "value": "(a+)+"}},
        }
        response = authenticated_client.post(f"/api/v1/experiments/{running_experiment.id}/versions/", payload,
                                             format="json")
        assert response.status_code == 400


@pytest.mark.django_db
class TestRateLimiting:
    def test_sdk_throttled_per_api_key(self, api_key, running_experiment, settings):
        settings.REST_FRAMEWORK = {**settings.REST_FRAMEWORK, "DEFAULT_THROTTLE_RATES": {
            **settings.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"], "sdk": "3/min"}}
        from rest_framework.throttling import SimpleRateThrottle

        SimpleRateThrottle.THROTTLE_RATES = settings.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"]
        try:
            client = APIClient()
            client.credentials(HTTP_X_API_KEY=api_key[1])
            body = {"user_id": "u1", "experiment_keys": [running_experiment.key]}
            codes = [client.post("/api/v1/evaluate/", body, format="json").status_code for _ in range(4)]
        finally:
            from rest_framework.settings import api_settings

            SimpleRateThrottle.THROTTLE_RATES = api_settings.DEFAULT_THROTTLE_RATES
        assert codes == [200, 200, 200, 429]

    def test_login_throttled(self, api_client, settings):
        from rest_framework.settings import api_settings
        from rest_framework.throttling import SimpleRateThrottle

        SimpleRateThrottle.THROTTLE_RATES = {**api_settings.DEFAULT_THROTTLE_RATES, "auth": "2/min"}
        try:
            codes = [api_client.post("/api/v1/auth/token/", {"email": "x@y.z", "password": "bad"},
                                     format="json").status_code for _ in range(3)]
        finally:
            SimpleRateThrottle.THROTTLE_RATES = api_settings.DEFAULT_THROTTLE_RATES
        assert codes == [401, 401, 429]


@pytest.mark.django_db
class TestAPIKeyRevocation:
    def test_admin_revokes(self, authenticated_client, api_key, running_experiment):
        key, raw = api_key
        response = authenticated_client.delete(f"/api/v1/auth/api-keys/{key.id}/")
        assert response.status_code == 204
        assert not APIKey.objects.get(id=key.id).is_active
        assert AuditLog.objects.filter(action=AuditAction.API_KEY_REVOKED).exists()

        client = APIClient()
        client.credentials(HTTP_X_API_KEY=raw)
        response = client.post("/api/v1/evaluate/", {"user_id": "u", "experiment_keys": ["x"]}, format="json")
        assert response.status_code in (401, 403)

    def test_manager_cannot_revoke(self, make_member, api_key):
        manager = make_member(Role.EXPERIMENT_MANAGER)
        assert manager.delete(f"/api/v1/auth/api-keys/{api_key[0].id}/").status_code == 403

    def test_outsider_gets_404(self, api_key):
        from conftest import UserFactory

        client = APIClient()
        client.force_authenticate(user=UserFactory())
        assert client.delete(f"/api/v1/auth/api-keys/{api_key[0].id}/").status_code == 404
