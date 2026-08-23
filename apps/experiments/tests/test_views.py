import pytest
from django.urls import reverse

from apps.experiments.models import ExperimentStatus
from conftest import ExperimentFactory, ExperimentVersionFactory, ProjectFactory, VariantFactory


@pytest.mark.django_db
class TestExperimentCRUD:
    def test_create_experiment(self, authenticated_client, project):
        url = reverse("experiment-list")
        data = {
            "project_id": str(project.id),
            "key": "checkout_v3",
            "name": "Checkout V3",
            "description": "Test new checkout",
        }
        response = authenticated_client.post(url, data, format="json")
        assert response.status_code == 201
        assert response.data["key"] == "checkout_v3"
        assert response.data["status"] == "DRAFT"

    def test_list_experiments(self, authenticated_client, project):
        ExperimentFactory(project=project)
        ExperimentFactory(project=project)
        url = reverse("experiment-list")
        response = authenticated_client.get(url, {"project": str(project.id)})
        assert response.status_code == 200
        assert response.data["count"] == 2

    def test_retrieve_experiment(self, authenticated_client, project):
        exp = ExperimentFactory(project=project)
        url = reverse("experiment-detail", args=[exp.id])
        response = authenticated_client.get(url)
        assert response.status_code == 200
        assert response.data["key"] == exp.key

    def test_transition_experiment(self, authenticated_client, project):
        exp = ExperimentFactory(project=project, status=ExperimentStatus.DRAFT)
        url = reverse("experiment-transition", args=[exp.id])
        response = authenticated_client.post(url, {"status": "REVIEW"}, format="json")
        assert response.status_code == 200
        assert response.data["status"] == "REVIEW"

    def test_invalid_transition(self, authenticated_client, project):
        exp = ExperimentFactory(project=project, status=ExperimentStatus.DRAFT)
        url = reverse("experiment-transition", args=[exp.id])
        response = authenticated_client.post(url, {"status": "RUNNING"}, format="json")
        assert response.status_code == 400

    def test_create_version(self, authenticated_client, project):
        exp = ExperimentFactory(project=project)
        # Auto-creates version 1, so next will be 2
        version = ExperimentVersionFactory(experiment=exp, version_number=1)
        exp.current_version = version
        exp.save()

        url = reverse("experiment-create-version", args=[exp.id])
        data = {
            "traffic_allocation": 10000,
            "variants": [
                {
                    "key": "control",
                    "name": "Control",
                    "is_control": True,
                    "traffic_percentage": 5000,
                    "bucket_start": 0,
                    "bucket_end": 4999,
                },
                {
                    "key": "treatment",
                    "name": "Treatment",
                    "is_control": False,
                    "traffic_percentage": 5000,
                    "bucket_start": 5000,
                    "bucket_end": 9999,
                },
            ],
            "targeting": {
                "rules_json": {
                    "operator": "AND",
                    "conditions": [
                        {"field": "user.country", "operator": "equals", "value": "IN"},
                    ],
                },
            },
        }
        response = authenticated_client.post(url, data, format="json")
        assert response.status_code == 201
        assert response.data["version_number"] == 2
        assert len(response.data["variants"]) == 2
        assert response.data["targeting"]["rules_json"]["operator"] == "AND"
