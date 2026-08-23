import pytest
from unittest.mock import MagicMock, patch

from rest_framework.test import APIClient


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
class TestExperimentResultsView:
    def test_results_include_statistical_analysis(self, authenticated_client, running_experiment):
        with patch("apps.events.views.query_experiment_results", return_value=MOCK_VARIANT_DATA):
            response = authenticated_client.get(
                f"/api/v1/experiments/{running_experiment.id}/results/"
            )

        assert response.status_code == 200
        data = response.data

        # Check structure
        assert "variants" in data
        assert "srm" in data
        assert "recommended_sample_size_per_variant" in data

        # Control should have CIs
        control = data["variants"]["control"]
        assert "ci_lower" in control
        assert "ci_upper" in control

        # Treatment should have lift and significance
        treatment = data["variants"]["treatment"]
        assert "lift" in treatment
        assert "p_value" in treatment
        assert "is_significant" in treatment
        assert treatment["is_significant"] is True

        # SRM
        assert data["srm"]["is_mismatch"] is False

    def test_results_empty_data(self, authenticated_client, running_experiment):
        with patch("apps.events.views.query_experiment_results", return_value={}):
            response = authenticated_client.get(
                f"/api/v1/experiments/{running_experiment.id}/results/"
            )

        assert response.status_code == 200
        assert response.data["variants"] == {}


@pytest.mark.django_db
class TestSRMCheckView:
    def test_srm_no_mismatch(self, authenticated_client, running_experiment):
        with patch("apps.events.views.query_experiment_results", return_value=MOCK_VARIANT_DATA):
            response = authenticated_client.get(
                f"/api/v1/experiments/{running_experiment.id}/results/srm/"
            )

        assert response.status_code == 200
        assert response.data["is_mismatch"] is False
        assert "No Sample Ratio Mismatch" in response.data["message"]

    def test_srm_with_mismatch(self, authenticated_client, running_experiment):
        imbalanced_data = {
            "control": {
                "exposures": 126000,
                "unique_users": 63000,
                "conversions": 6300,
                "conversion_rate": 0.10,
            },
            "treatment": {
                "exposures": 74000,
                "unique_users": 37000,
                "conversions": 3700,
                "conversion_rate": 0.10,
            },
        }
        with patch("apps.events.views.query_experiment_results", return_value=imbalanced_data):
            response = authenticated_client.get(
                f"/api/v1/experiments/{running_experiment.id}/results/srm/"
            )

        assert response.status_code == 200
        assert response.data["is_mismatch"] is True
        assert "Sample Ratio Mismatch detected" in response.data["message"]

    def test_srm_not_found(self, authenticated_client):
        import uuid
        response = authenticated_client.get(
            f"/api/v1/experiments/{uuid.uuid4()}/results/srm/"
        )
        assert response.status_code == 404

    def test_srm_requires_auth(self, api_client, running_experiment):
        response = api_client.get(
            f"/api/v1/experiments/{running_experiment.id}/results/srm/"
        )
        assert response.status_code in (401, 403)
