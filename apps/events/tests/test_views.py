from unittest.mock import MagicMock

import pytest
from rest_framework.test import APIClient


class TestTrackEventView:
    def test_track_event_requires_api_key(self, api_client):
        response = api_client.post(
            "/api/v1/events/track/",
            {"user_id": "user-1", "event_name": "purchase"},
            format="json",
        )
        assert response.status_code == 401

    def test_track_event_accepted(self, api_client, api_key, mock_kafka):
        key_instance, raw_key = api_key
        client = APIClient()
        client.credentials(HTTP_X_API_KEY=raw_key)

        response = client.post(
            "/api/v1/events/track/",
            {
                "user_id": "user-100",
                "event_name": "purchase",
                "value": 29.99,
                "metadata": {"currency": "USD"},
            },
            format="json",
        )

        assert response.status_code == 202
        assert response.data["status"] == "accepted"
        assert "event_id" in response.data

    def test_track_event_with_custom_event_id(self, api_client, api_key, mock_kafka):
        key_instance, raw_key = api_key
        client = APIClient()
        client.credentials(HTTP_X_API_KEY=raw_key)

        response = client.post(
            "/api/v1/events/track/",
            {
                "event_id": "custom-evt-123",
                "user_id": "user-100",
                "event_name": "signup",
            },
            format="json",
        )

        assert response.status_code == 202
        assert response.data["event_id"] == "custom-evt-123"

    def test_track_event_validation(self, api_client, api_key):
        key_instance, raw_key = api_key
        client = APIClient()
        client.credentials(HTTP_X_API_KEY=raw_key)

        # Missing required fields
        response = client.post(
            "/api/v1/events/track/",
            {"user_id": "user-100"},
            format="json",
        )
        assert response.status_code == 400


@pytest.mark.django_db
class TestExperimentResultsView:
    def test_results_requires_auth(self, api_client, running_experiment):
        response = api_client.get(
            f"/api/v1/experiments/{running_experiment.id}/results/"
        )
        assert response.status_code in (401, 403)

    def test_results_returns_data(self, authenticated_client, running_experiment, mock_clickhouse):
        # Mock ClickHouse to return sample data
        mock_clickhouse.query.return_value = MagicMock(result_rows=[])

        response = authenticated_client.get(
            f"/api/v1/experiments/{running_experiment.id}/results/"
        )

        assert response.status_code == 200
        assert response.data["experiment_id"] == str(running_experiment.id)
        assert response.data["experiment_key"] == "test-experiment"
        assert "variants" in response.data

    def test_results_not_found(self, authenticated_client):
        import uuid
        response = authenticated_client.get(
            f"/api/v1/experiments/{uuid.uuid4()}/results/"
        )
        assert response.status_code == 404


@pytest.mark.django_db
class TestAutoExposureTracking:
    def test_evaluate_produces_exposure_event(self, api_key, running_experiment, mock_kafka):
        """Verify that evaluating an experiment auto-produces an exposure event."""
        key_instance, raw_key = api_key

        # Ensure experiment belongs to the API key's project
        running_experiment.project = key_instance.project
        running_experiment.save()

        client = APIClient()
        client.credentials(HTTP_X_API_KEY=raw_key)

        response = client.post(
            "/api/v1/evaluate/",
            {
                "user_id": "user-500",
                "experiment_keys": [running_experiment.key],
                "context": {},
            },
            format="json",
        )

        assert response.status_code == 200
        result = response.data["evaluations"][running_experiment.key]
        assert result["assigned"] is True

        # Kafka producer should have been called for the exposure
        mock_kafka.produce.assert_called()
