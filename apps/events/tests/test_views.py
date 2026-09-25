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


@pytest.mark.django_db
class TestQueryExperimentResults:
    def test_single_query_maps_rows(self, running_experiment, mock_clickhouse):
        from apps.events.clickhouse import query_experiment_results

        mock_clickhouse.query.return_value = MagicMock(result_rows=[
            ("control", 1200, 1000, 100),
            ("treatment", 1300, 1000, 120),
        ])
        results = query_experiment_results(running_experiment.id)
        assert results["treatment"] == {
            "exposures": 1300, "unique_users": 1000, "conversions": 120, "conversion_rate": 0.12,
        }
        assert mock_clickhouse.query.call_count == 1
        params = mock_clickhouse.query.call_args.kwargs["parameters"]
        assert params == {"experiment_id": str(running_experiment.id), "event_name": ""}

    def test_uses_primary_metric_event(self, running_experiment, mock_clickhouse):
        from apps.events.clickhouse import query_experiment_results
        from apps.stats.models import ExperimentMetric, MetricType

        ExperimentMetric.objects.create(experiment=running_experiment, name="Checkout", event_name="purchase",
                                        metric_type=MetricType.PRIMARY)
        query_experiment_results(running_experiment.id)
        assert mock_clickhouse.query.call_args.kwargs["parameters"]["event_name"] == "purchase"

    def test_query_failure_returns_empty(self, running_experiment, mock_clickhouse):
        from apps.events.clickhouse import query_experiment_results

        mock_clickhouse.query.side_effect = Exception("down")
        assert query_experiment_results(running_experiment.id) == {}


class TestParseEventTime:
    def test_iso_with_offset_becomes_naive_utc(self):
        from datetime import datetime

        from apps.events.clickhouse import parse_event_time

        assert parse_event_time("2026-09-01T12:30:00+05:30") == datetime(2026, 9, 1, 7, 0, 0)
        assert parse_event_time("2026-09-01T07:00:00.123Z") == datetime(2026, 9, 1, 7, 0, 0)

    def test_garbage_becomes_now(self):
        from datetime import datetime

        from apps.events.clickhouse import parse_event_time

        value = parse_event_time("not a date")
        assert isinstance(value, datetime) and value.tzinfo is None

    def test_inserts_send_datetime_objects(self, mock_clickhouse):
        from datetime import datetime

        from apps.events.clickhouse import insert_conversion, insert_exposure

        insert_exposure({"event_id": "e1", "user_id": "u1", "timestamp": "2026-09-01T07:00:00Z"})
        insert_conversion({"event_id": "c1", "user_id": "u1", "timestamp": "2026-09-01T07:00:00Z"})
        for call in mock_clickhouse.insert.call_args_list:
            row = call.args[1][0]
            assert isinstance(row[-1], datetime)


@pytest.mark.django_db
class TestUnequalSplitSRM:
    def test_srm_uses_version_split(self, authenticated_client, running_experiment):
        from unittest.mock import patch

        version = running_experiment.current_version
        control = version.variants.get(key="control")
        treatment = version.variants.get(key="treatment")
        control.traffic_percentage, control.bucket_end = 2000, 1999
        treatment.traffic_percentage, treatment.bucket_start = 8000, 2000
        control.save()
        treatment.save()
        data = {
            "control": {"exposures": 2000, "unique_users": 2000, "conversions": 200, "conversion_rate": 0.1},
            "treatment": {"exposures": 8000, "unique_users": 8000, "conversions": 800, "conversion_rate": 0.1},
        }
        with patch("apps.events.views.query_experiment_results", return_value=data):
            response = authenticated_client.get(f"/api/v1/experiments/{running_experiment.id}/results/srm/")
        assert response.data["is_mismatch"] is False
        assert response.data["expected_proportions"] == {"control": 0.2, "treatment": 0.8}

    def test_zero_control_rate_serializes(self, authenticated_client, running_experiment):
        from unittest.mock import patch

        data = {
            "control": {"exposures": 1000, "unique_users": 1000, "conversions": 0, "conversion_rate": 0.0},
            "treatment": {"exposures": 1000, "unique_users": 1000, "conversions": 50, "conversion_rate": 0.05},
        }
        with patch("apps.events.views.query_experiment_results", return_value=data):
            response = authenticated_client.get(f"/api/v1/experiments/{running_experiment.id}/results/")
        assert response.status_code == 200
        assert response.data["variants"]["treatment"]["lift"] is None
        response = authenticated_client.get("/api/v1/experiments/?page_size=1")
        assert response.data["results"][0]["project"] == running_experiment.project_id
