from unittest.mock import MagicMock

import pytest
from rest_framework import status

from conftest import ExperimentFactory


@pytest.fixture
def key_client(api_key):
    from rest_framework.test import APIClient

    client = APIClient()
    client.credentials(HTTP_X_API_KEY=api_key[1])
    return client


@pytest.mark.django_db
class TestTelemetryIngestView:
    def test_ingest_single_point(self, key_client, running_experiment, mock_clickhouse):
        response = key_client.post(
            "/api/v1/observability/telemetry/",
            {
                "experiment_id": str(running_experiment.id),
                "variant_key": "control",
                "metric_name": "latency_ms",
                "metric_value": 42.5,
            },
            format="json",
        )
        assert response.status_code == status.HTTP_202_ACCEPTED
        assert response.data["status"] == "accepted"
        mock_clickhouse.insert.assert_called_once()

    def test_ingest_with_event_time(self, key_client, running_experiment, mock_clickhouse):
        response = key_client.post(
            "/api/v1/observability/telemetry/",
            {
                "experiment_id": str(running_experiment.id),
                "variant_key": "treatment",
                "metric_name": "error_rate",
                "metric_value": 0.05,
                "event_time": "2024-01-15T10:30:00Z",
            },
            format="json",
        )
        assert response.status_code == status.HTTP_202_ACCEPTED

    def test_ingest_missing_fields(self, key_client):
        response = key_client.post(
            "/api/v1/observability/telemetry/",
            {"experiment_id": "exp-1"},
            format="json",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_ingest_requires_api_key(self, api_client, running_experiment):
        response = api_client.post(
            "/api/v1/observability/telemetry/",
            {
                "experiment_id": str(running_experiment.id),
                "variant_key": "control",
                "metric_name": "latency_ms",
                "metric_value": 1.0,
            },
            format="json",
        )
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_ingest_rejects_other_projects_experiment(self, key_client, mock_clickhouse):
        other = ExperimentFactory()
        response = key_client.post(
            "/api/v1/observability/telemetry/",
            {
                "experiment_id": str(other.id),
                "variant_key": "control",
                "metric_name": "latency_ms",
                "metric_value": 1.0,
            },
            format="json",
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND
        mock_clickhouse.insert.assert_not_called()


@pytest.mark.django_db
class TestTelemetryBatchIngestView:
    def test_batch_ingest(self, key_client, running_experiment, mock_clickhouse):
        exp_id = str(running_experiment.id)
        response = key_client.post(
            "/api/v1/observability/telemetry/batch/",
            {
                "data_points": [
                    {
                        "experiment_id": exp_id,
                        "variant_key": "control",
                        "metric_name": "latency_ms",
                        "metric_value": 42.5,
                    },
                    {
                        "experiment_id": exp_id,
                        "variant_key": "treatment",
                        "metric_name": "latency_ms",
                        "metric_value": 55.0,
                    },
                ],
            },
            format="json",
        )
        assert response.status_code == status.HTTP_202_ACCEPTED
        assert response.data["ingested"] == 2

    def test_batch_empty(self, key_client, mock_clickhouse):
        response = key_client.post(
            "/api/v1/observability/telemetry/batch/",
            {"data_points": []},
            format="json",
        )
        assert response.status_code == status.HTTP_202_ACCEPTED
        assert response.data["ingested"] == 0

    def test_batch_rejects_unknown_experiment(self, key_client, running_experiment, mock_clickhouse):
        import uuid

        response = key_client.post(
            "/api/v1/observability/telemetry/batch/",
            {
                "data_points": [
                    {
                        "experiment_id": str(running_experiment.id),
                        "variant_key": "control",
                        "metric_name": "latency_ms",
                        "metric_value": 1.0,
                    },
                    {
                        "experiment_id": str(uuid.uuid4()),
                        "variant_key": "control",
                        "metric_name": "latency_ms",
                        "metric_value": 1.0,
                    },
                ],
            },
            format="json",
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND
        mock_clickhouse.insert.assert_not_called()


@pytest.mark.django_db
class TestMetricsEndpoint:
    def test_metrics_exposed(self, api_client):
        api_client.get("/api/v1/auth/me/")
        response = api_client.get("/metrics")
        assert response.status_code == 200
        body = response.content.decode()
        assert "http_requests_total" in body
        assert "experiment_evaluations_total" in body


@pytest.mark.django_db
class TestProductionImpactView:
    def test_no_telemetry_data(self, authenticated_client, running_experiment, mock_clickhouse):
        mock_clickhouse.query.return_value = MagicMock(result_rows=[])
        response = authenticated_client.get(
            f"/api/v1/experiments/{running_experiment.id}/production-impact/",
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.data["impact"] == {}
        assert response.data["anomalies"] == []
        assert "No telemetry data" in response.data["message"]

    def test_with_telemetry_data(self, authenticated_client, running_experiment, mock_clickhouse):
        mock_clickhouse.query.return_value = MagicMock(
            result_rows=[
                ("control", "latency_ms", 1000, 100.0, 90.0, 180.0, 200.0, 10.0, 300.0),
                ("treatment", "latency_ms", 1000, 150.0, 140.0, 250.0, 280.0, 20.0, 400.0),
            ]
        )
        response = authenticated_client.get(
            f"/api/v1/experiments/{running_experiment.id}/production-impact/",
        )
        assert response.status_code == status.HTTP_200_OK
        assert "treatment" in response.data["impact"]
        assert len(response.data["anomalies"]) > 0

    def test_experiment_not_found(self, authenticated_client):
        import uuid

        fake_id = uuid.uuid4()
        response = authenticated_client.get(
            f"/api/v1/experiments/{fake_id}/production-impact/",
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_unauthenticated(self, api_client, running_experiment):
        response = api_client.get(
            f"/api/v1/experiments/{running_experiment.id}/production-impact/",
        )
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
