import pytest
from django.urls import reverse


@pytest.mark.django_db
class TestEvaluateView:
    def test_evaluate_single_experiment(self, api_client, api_key, running_experiment):
        key_obj, raw_key = api_key
        url = reverse("evaluate")
        data = {
            "user_id": "user-123",
            "experiment_keys": [running_experiment.key],
            "context": {"user": {"country": "IN"}},
        }
        response = api_client.post(
            url, data, format="json",
            HTTP_X_API_KEY=raw_key,
        )
        assert response.status_code == 200
        evaluations = response.data["evaluations"]
        assert running_experiment.key in evaluations
        result = evaluations[running_experiment.key]
        assert result["assigned"] is True
        assert result["variant_key"] in ("control", "treatment")

    def test_evaluate_missing_experiment(self, api_client, api_key, running_experiment):
        _, raw_key = api_key
        url = reverse("evaluate")
        data = {
            "user_id": "user-123",
            "experiment_keys": ["nonexistent"],
            "context": {},
        }
        response = api_client.post(url, data, format="json", HTTP_X_API_KEY=raw_key)
        assert response.status_code == 200
        result = response.data["evaluations"]["nonexistent"]
        assert result["assigned"] is False
        assert result["reason"] == "experiment_not_found"

    def test_evaluate_without_api_key(self, api_client):
        url = reverse("evaluate")
        data = {"user_id": "user-123", "experiment_keys": ["exp"], "context": {}}
        response = api_client.post(url, data, format="json")
        assert response.status_code == 401

    def test_evaluate_deterministic(self, api_client, api_key, running_experiment):
        _, raw_key = api_key
        url = reverse("evaluate")
        data = {
            "user_id": "user-abc",
            "experiment_keys": [running_experiment.key],
            "context": {},
        }
        r1 = api_client.post(url, data, format="json", HTTP_X_API_KEY=raw_key)
        r2 = api_client.post(url, data, format="json", HTTP_X_API_KEY=raw_key)
        assert r1.data == r2.data


@pytest.mark.django_db
class TestEvaluateDebugView:
    def test_debug_endpoint(self, authenticated_client, running_experiment):
        url = reverse("evaluate-debug")
        data = {
            "user_id": "user-123",
            "experiment_key": running_experiment.key,
            "context": {},
        }
        response = authenticated_client.post(url, data, format="json")
        assert response.status_code == 200
        assert "evaluation_steps" in response.data
        assert "result" in response.data
        assert len(response.data["evaluation_steps"]) >= 4

    def test_debug_not_found(self, authenticated_client):
        url = reverse("evaluate-debug")
        data = {
            "user_id": "user-123",
            "experiment_key": "nonexistent",
            "context": {},
        }
        response = authenticated_client.post(url, data, format="json")
        assert response.status_code == 404
