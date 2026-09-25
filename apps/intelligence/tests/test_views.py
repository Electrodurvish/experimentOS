from unittest.mock import patch

import pytest

from apps.intelligence.models import TimelineEvent, TimelineEventType, record_timeline_event

MOCK_VARIANT_DATA = {
    "control": {
        "exposures": 100000,
        "unique_users": 50000,
        "conversions": 5000,
        "conversion_rate": 0.10,
    },
    "treatment": {
        "exposures": 100000,
        "unique_users": 50000,
        "conversions": 6000,
        "conversion_rate": 0.12,
    },
}


@pytest.mark.django_db
class TestExperimentHealthView:
    def test_health_endpoint(self, authenticated_client, running_experiment):
        with patch("apps.intelligence.views.query_experiment_results", return_value=MOCK_VARIANT_DATA):
            response = authenticated_client.get(
                f"/api/v1/experiments/{running_experiment.id}/health/"
            )

        assert response.status_code == 200
        assert "health" in response.data
        assert "overall_score" in response.data["health"]
        assert "dimensions" in response.data["health"]
        assert response.data["health"]["overall_score"] >= 0

    def test_health_not_found(self, authenticated_client):
        import uuid
        response = authenticated_client.get(
            f"/api/v1/experiments/{uuid.uuid4()}/health/"
        )
        assert response.status_code == 404

    def test_health_requires_auth(self, api_client, running_experiment):
        response = api_client.get(
            f"/api/v1/experiments/{running_experiment.id}/health/"
        )
        assert response.status_code in (401, 403)


@pytest.mark.django_db
class TestExperimentSegmentsView:
    def test_segments_endpoint(self, authenticated_client, running_experiment):
        segment_data = [
            {
                "dimension": "platform",
                "value": "android",
                "control": {"users": 20000, "conversions": 2000},
                "treatment": {"users": 20000, "conversions": 2800},
            },
        ]

        with patch("apps.intelligence.views.query_experiment_results", return_value=MOCK_VARIANT_DATA):
            response = authenticated_client.post(
                f"/api/v1/experiments/{running_experiment.id}/segments/",
                {"segments": segment_data, "aggregate_lift": 0.20},
                format="json",
            )

        assert response.status_code == 200
        assert "analysis" in response.data
        assert "segments" in response.data["analysis"]
        assert "paradox_detected" in response.data["analysis"]
        assert "top_contributors" in response.data["analysis"]

    def test_segments_empty(self, authenticated_client, running_experiment):
        with patch("apps.intelligence.views.query_experiment_results", return_value={}):
            response = authenticated_client.post(
                f"/api/v1/experiments/{running_experiment.id}/segments/",
                {"segments": []},
                format="json",
            )

        assert response.status_code == 200


@pytest.mark.django_db
class TestExperimentTimelineView:
    def test_timeline_empty(self, authenticated_client, running_experiment):
        response = authenticated_client.get(
            f"/api/v1/experiments/{running_experiment.id}/timeline/"
        )

        assert response.status_code == 200
        assert response.data["timeline"] == []

    def test_timeline_with_events(self, authenticated_client, running_experiment):
        record_timeline_event(
            experiment=running_experiment,
            event_type=TimelineEventType.EXPERIMENT_STARTED,
            title="Experiment started",
            detail="Experiment was started with 100% traffic.",
        )
        record_timeline_event(
            experiment=running_experiment,
            event_type=TimelineEventType.HEALTH_SCORE_CHANGED,
            title="Health score: 82/100",
            metadata={"score": 82},
        )

        response = authenticated_client.get(
            f"/api/v1/experiments/{running_experiment.id}/timeline/"
        )

        assert response.status_code == 200
        assert len(response.data["timeline"]) == 2
        # Ordered by created_at ascending
        assert response.data["timeline"][0]["event_type"] == "experiment_started"
        assert response.data["timeline"][1]["event_type"] == "health_score_changed"

    def test_timeline_not_found(self, authenticated_client):
        import uuid
        response = authenticated_client.get(
            f"/api/v1/experiments/{uuid.uuid4()}/timeline/"
        )
        assert response.status_code == 404


@pytest.mark.django_db
class TestRecordTimelineEvent:
    def test_record_event(self, running_experiment):
        event = record_timeline_event(
            experiment=running_experiment,
            event_type=TimelineEventType.SRM_DETECTED,
            title="SRM detected",
            detail="Expected 50/50, observed 63/37.",
            metadata={"chi_squared": 12.5, "p_value": 0.0004},
        )

        assert event.pk is not None
        assert event.event_type == "srm_detected"
        assert event.metadata["chi_squared"] == 12.5
        assert TimelineEvent.objects.count() == 1
