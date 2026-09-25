from datetime import timedelta

import pytest
from django.utils import timezone

from apps.decisions.models import RolloutAction
from apps.decisions.rollout import change_rollout
from apps.engine.assigner import evaluate_experiment
from apps.experiments.models import ExperimentStatus
from apps.experiments.state_machine import ExperimentStateMachine
from conftest import ExperimentFactory, UserFactory


@pytest.mark.django_db
class TestUserDebug:
    def test_explains_assignment_with_config_at_assignment(self, authenticated_client, running_experiment,
                                                           mock_cassandra):
        evaluate_experiment(running_experiment, "82931", {"country": "IN"})
        response = authenticated_client.get(
            f"/api/v1/experiments/{running_experiment.id}/users/82931/debug/"
        )
        assert response.status_code == 200
        data = response.data
        assert data["context"] == {"country": "IN"}  # reused from the recorded assignment
        assert data["result"]["assigned"] is True
        assert data["result"]["source"] == "sticky"
        assert data["explanation"][0].startswith("✓ Experiment is RUNNING")
        assert any("Sticky assignment found" in line for line in data["explanation"])
        recorded = data["recorded_assignment"]
        assert recorded["variant_key"] == data["result"]["variant_key"]
        assert recorded["config_at_assignment"]["version_number"] == 1
        assert {v["key"] for v in recorded["config_at_assignment"]["variants"]} == {"control", "treatment"}
        assert data["sticky"]["variant_key"] == recorded["variant_key"]

    def test_explicit_context_and_no_side_effects(self, authenticated_client, running_experiment, mock_cassandra):
        response = authenticated_client.get(
            f"/api/v1/experiments/{running_experiment.id}/users/new-user/debug/",
            {"context": '{"platform": "android"}'},
        )
        assert response.data["context"] == {"platform": "android"}
        assert response.data["recorded_assignment"] is None
        assert mock_cassandra == {}

    def test_bad_context(self, authenticated_client, running_experiment):
        url = f"/api/v1/experiments/{running_experiment.id}/users/u/debug/"
        assert authenticated_client.get(url, {"context": "{nope"}).status_code == 400
        assert authenticated_client.get(url, {"context": "[1]"}).status_code == 400

    def test_outsider_404(self, running_experiment):
        from rest_framework.test import APIClient

        client = APIClient()
        client.force_authenticate(user=UserFactory())
        assert client.get(f"/api/v1/experiments/{running_experiment.id}/users/u/debug/").status_code == 404


@pytest.mark.django_db
class TestUserAssignments:
    def test_lists_assignments_scoped(self, authenticated_client, running_experiment, mock_cassandra):
        evaluate_experiment(running_experiment, "u-1", {})
        response = authenticated_client.get("/api/v1/users/u-1/assignments/")
        [row] = response.data["assignments"]
        assert row["experiment_key"] == running_experiment.key
        assert row["version_number"] == 1

        from rest_framework.test import APIClient

        outsider = APIClient()
        outsider.force_authenticate(user=UserFactory())
        assert outsider.get("/api/v1/users/u-1/assignments/").data["assignments"] == []


@pytest.mark.django_db
class TestTimeTravel:
    def test_reconstructs_status_rollout_and_version(self, authenticated_client, project, user):
        experiment = ExperimentFactory(project=project, status=ExperimentStatus.DRAFT)
        from conftest import ExperimentVersionFactory, VariantFactory

        v1 = ExperimentVersionFactory(experiment=experiment, version_number=1)
        VariantFactory(version=v1, key="control", is_control=True, bucket_start=0, bucket_end=4999)
        VariantFactory(version=v1, key="treatment", bucket_start=5000, bucket_end=9999)
        experiment.current_version = v1
        experiment.save()

        sm = ExperimentStateMachine(experiment)
        for s in (ExperimentStatus.REVIEW, ExperimentStatus.APPROVED, ExperimentStatus.RUNNING):
            sm.transition_to(s)
        t_running = timezone.now()
        change_rollout(experiment, 5000, RolloutAction.MANUAL, "ramp")
        t_half = timezone.now()
        change_rollout(experiment, 1000, RolloutAction.ROLLBACK, "errors")
        sm.transition_to(ExperimentStatus.PAUSED)

        url = f"/api/v1/experiments/{experiment.id}/history/"
        before = authenticated_client.get(url, {"at": t_running.isoformat()}).data
        assert before["status"] == "RUNNING"
        assert before["rollout_percentage"] == 10000
        assert before["version"]["version_number"] == 1

        mid = authenticated_client.get(url, {"at": t_half.isoformat()}).data
        assert mid["rollout_percentage"] == 5000

        now = authenticated_client.get(url, {"at": (timezone.now() + timedelta(seconds=1)).isoformat()}).data
        assert now["status"] == "PAUSED"
        assert now["rollout_percentage"] == 1000

    def test_invalid_and_before_creation(self, authenticated_client, running_experiment):
        url = f"/api/v1/experiments/{running_experiment.id}/history/"
        assert authenticated_client.get(url, {"at": "yesterday"}).status_code == 400
        old = (running_experiment.created_at - timedelta(days=1)).isoformat()
        assert authenticated_client.get(url, {"at": old}).status_code == 404
