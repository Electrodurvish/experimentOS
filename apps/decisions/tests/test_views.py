import uuid
from unittest.mock import patch

import pytest

from apps.decisions.models import Guardrail, RolloutChange

RESULTS = {
    "control": {"exposures": 70000, "unique_users": 60000, "conversions": 6000, "conversion_rate": 0.10},
    "treatment": {"exposures": 70000, "unique_users": 60000, "conversions": 7200, "conversion_rate": 0.12},
}


@pytest.fixture(autouse=True)
def results():
    with patch("apps.decisions.context.query_experiment_results", return_value=RESULTS):
        yield


def url(experiment, suffix):
    return f"/api/v1/experiments/{experiment.id}/{suffix}/"


@pytest.mark.django_db
class TestGuardrailViews:
    def test_crud(self, authenticated_client, running_experiment):
        payload = {"name": "Error rate", "metric_name": "error_rate", "operator": "ABSOLUTE_GT", "threshold": 5}
        response = authenticated_client.post(url(running_experiment, "guardrails"), payload, format="json")
        assert response.status_code == 201
        gid = response.data["id"]
        assert response.data["action"] == "ROLLBACK"

        response = authenticated_client.get(url(running_experiment, "guardrails"))
        assert len(response.data) == 1

        response = authenticated_client.patch(f"{url(running_experiment, 'guardrails')}{gid}/",
                                              {"threshold": 3}, format="json")
        assert response.data["threshold"] == 3

        response = authenticated_client.delete(f"{url(running_experiment, 'guardrails')}{gid}/")
        assert response.status_code == 204
        assert not Guardrail.objects.exists()

    def test_requires_auth(self, api_client, running_experiment):
        assert api_client.get(url(running_experiment, "guardrails")).status_code == 401


@pytest.mark.django_db
class TestRolloutPolicyView:
    def test_default_then_update(self, authenticated_client, running_experiment):
        response = authenticated_client.get(url(running_experiment, "rollout-policy"))
        assert response.data["stages"] == [1000, 2500, 5000, 10000]
        response = authenticated_client.put(url(running_experiment, "rollout-policy"),
                                            {"stages": [500, 5000, 10000], "auto_advance": True}, format="json")
        assert response.status_code == 200
        assert response.data["auto_advance"] is True

    def test_rejects_unsorted_stages(self, authenticated_client, running_experiment):
        response = authenticated_client.put(url(running_experiment, "rollout-policy"),
                                            {"stages": [5000, 1000]}, format="json")
        assert response.status_code == 400


@pytest.mark.django_db
class TestRolloutViews:
    def test_manual_rollout_and_history(self, authenticated_client, running_experiment):
        response = authenticated_client.post(url(running_experiment, "rollout"),
                                             {"percentage": 5000, "reason": "Manual rollout"}, format="json")
        assert response.status_code == 200
        assert response.data == {**response.data, "from": 100, "to": 50, "action": "manual"}

        response = authenticated_client.get(url(running_experiment, "rollout"))
        assert response.data["rollout_percentage"] == 5000
        assert len(response.data["history"]) == 1

    def test_rollback_defaults_to_policy(self, authenticated_client, running_experiment):
        response = authenticated_client.post(url(running_experiment, "rollback"), {}, format="json")
        assert response.status_code == 200
        assert response.data["to"] == 10
        assert RolloutChange.objects.get().action == "rollback"

    def test_rollback_must_decrease(self, authenticated_client, running_experiment):
        running_experiment.rollout_percentage = 1000
        running_experiment.save()
        response = authenticated_client.post(url(running_experiment, "rollback"), {"to_percentage": 5000},
                                             format="json")
        assert response.status_code == 400

    def test_not_found(self, authenticated_client):
        response = authenticated_client.get(f"/api/v1/experiments/{uuid.uuid4()}/rollout/")
        assert response.status_code == 404


@pytest.mark.django_db
class TestDecisionViews:
    def test_preview_does_not_persist(self, authenticated_client, running_experiment):
        response = authenticated_client.get(url(running_experiment, "decision"))
        assert response.status_code == 200
        assert response.data["recommendation"] == "COMPLETE"
        assert response.data["evidence"]
        assert not running_experiment.decisions.exists()

    def test_post_persists_and_applies(self, authenticated_client, running_experiment):
        running_experiment.rollout_percentage = 2500
        running_experiment.save()
        response = authenticated_client.post(url(running_experiment, "decision"), {"apply": True}, format="json")
        assert response.status_code == 201
        assert response.data["recommendation"] == "INCREASE_ROLLOUT"
        assert response.data["applied"] == {"action": "increase", "from": 2500, "to": 5000}

        response = authenticated_client.get(url(running_experiment, "decisions"))
        assert response.data["count"] == 1

    def test_post_with_segments(self, authenticated_client, running_experiment):
        running_experiment.rollout_percentage = 2500
        running_experiment.save()
        segments = [{"dimension": "platform", "value": "android",
                     "control": {"users": 20000, "conversions": 2400},
                     "treatment": {"users": 20000, "conversions": 1600}}]
        response = authenticated_client.post(url(running_experiment, "decision"), {"segments": segments},
                                             format="json")
        assert response.data["recommendation"] == "CONTINUE"

    def test_anomalies(self, authenticated_client, running_experiment):
        response = authenticated_client.get(url(running_experiment, "anomalies"))
        assert response.status_code == 200
        assert response.data["anomalies"] == []


@pytest.mark.django_db
class TestExperimentActions:
    def test_pause_and_start(self, authenticated_client, running_experiment):
        response = authenticated_client.post(f"/api/v1/experiments/{running_experiment.id}/pause/",
                                             {"reason": "investigate"}, format="json")
        assert response.status_code == 200
        assert response.data["status"] == "PAUSED"
        response = authenticated_client.post(f"/api/v1/experiments/{running_experiment.id}/start/")
        assert response.data["status"] == "RUNNING"

        from apps.intelligence.models import TimelineEvent
        types = list(TimelineEvent.objects.order_by("created_at").values_list("event_type", flat=True))
        assert types == ["experiment_paused", "experiment_resumed"]


@pytest.mark.django_db
class TestInteractionView:
    def test_detect(self, authenticated_client):
        pair = {"experiment_a": "a", "experiment_b": "b",
                "a_only": {"users": 5000, "conversions": 600}, "b_only": {"users": 5000, "conversions": 600},
                "both": {"users": 5000, "conversions": 300}, "neither": {"users": 5000, "conversions": 500}}
        response = authenticated_client.post("/api/v1/interactions/", {"pairs": [pair]}, format="json")
        assert response.status_code == 200
        assert response.data["interactions"][0]["is_interaction"] is True
        assert response.data["graph"]["edges"][0]["type"] == "antagonistic"
