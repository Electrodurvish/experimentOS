from unittest.mock import MagicMock, patch

import pytest

from apps.decisions.guardrails import evaluate_guardrails
from apps.decisions.models import Guardrail, GuardrailOperator, GuardrailSource
from apps.stats.engine import mean_difference_test
from apps.stats.metrics import analyze_metric
from apps.stats.models import ExperimentMetric, MetricAggregation, MetricType


class TestMeanDifferenceTest:
    def test_detects_difference(self):
        result = mean_difference_test(10.0, 25.0, 5000, 10.5, 25.0, 5000)
        assert result["difference"] == 0.5
        assert result["lift"] == pytest.approx(0.05)
        assert result["p_value"] < 0.001
        assert result["ci_lower"] < 0.5 < result["ci_upper"]

    def test_no_difference(self):
        assert mean_difference_test(10.0, 25.0, 5000, 10.0, 25.0, 5000)["p_value"] == 1.0

    def test_small_samples(self):
        assert mean_difference_test(1, 1, 1, 2, 1, 1)["p_value"] == 1.0

    def test_zero_control_mean(self):
        assert mean_difference_test(0.0, 1.0, 100, 1.0, 1.0, 100)["lift"] is None


class TestAnalyzeMetric:
    def test_conversion_metric(self):
        metric = ExperimentMetric(name="Refund rate", event_name="refund", metric_type=MetricType.GUARDRAIL)
        data = {"control": {"users": 10000, "converters": 200, "total_value": 0, "total_value_sq": 0},
                "treatment": {"users": 10000, "converters": 300, "total_value": 0, "total_value_sq": 0}}
        result = analyze_metric(metric, data)
        t = result["variants"]["treatment"]
        assert t["value"] == 0.03 and t["lift"] == pytest.approx(0.5)
        assert t["is_significant"] is True
        assert "ci_lower" in result["variants"]["control"]

    def test_mean_value_metric(self):
        metric = ExperimentMetric(name="Revenue", event_name="purchase", metric_type=MetricType.SECONDARY,
                                  aggregation=MetricAggregation.MEAN_VALUE)
        # control: 1000 users, mean 5, treatment: 1000 users, mean 6, both with variance ~ 100
        data = {
            "control": {"users": 1000, "converters": 400, "total_value": 5000.0,
                        "total_value_sq": 1000 * (100 + 25.0)},
            "treatment": {"users": 1000, "converters": 450, "total_value": 6000.0,
                          "total_value_sq": 1000 * (100 + 36.0)},
        }
        t = analyze_metric(metric, data)["variants"]["treatment"]
        assert t["value"] == 6.0
        assert t["lift"] == pytest.approx(0.2)
        assert t["variance"] == pytest.approx(100.1, rel=1e-3)
        assert t["is_significant"] is True


@pytest.mark.django_db
class TestMetricViews:
    def url(self, experiment, suffix=""):
        return f"/api/v1/experiments/{experiment.id}/metrics/{suffix}"

    def test_crud_and_single_primary(self, authenticated_client, running_experiment):
        response = authenticated_client.post(self.url(running_experiment), {
            "name": "Purchase conversion", "event_name": "purchase", "metric_type": "PRIMARY"}, format="json")
        assert response.status_code == 201
        response = authenticated_client.post(self.url(running_experiment), {
            "name": "Other", "event_name": "signup", "metric_type": "PRIMARY"}, format="json")
        assert response.status_code == 400
        response = authenticated_client.post(self.url(running_experiment), {
            "name": "Revenue", "event_name": "purchase", "metric_type": "SECONDARY",
            "aggregation": "MEAN_VALUE"}, format="json")
        assert response.status_code == 201
        assert len(authenticated_client.get(self.url(running_experiment)).data) == 2

    def test_results(self, authenticated_client, running_experiment, mock_clickhouse):
        ExperimentMetric.objects.create(experiment=running_experiment, name="Revenue", event_name="purchase",
                                        metric_type=MetricType.SECONDARY, aggregation=MetricAggregation.MEAN_VALUE)
        mock_clickhouse.query.return_value = MagicMock(result_rows=[
            ("control", 1000, 400, 5000.0, 125000.0),
            ("treatment", 1000, 450, 6000.0, 136000.0),
        ])
        response = authenticated_client.get(self.url(running_experiment, "results/"))
        assert response.status_code == 200
        [metric] = response.data["metrics"]
        assert metric["variants"]["treatment"]["value"] == 6.0
        assert mock_clickhouse.query.call_args.kwargs["parameters"]["event_name"] == "purchase"

    def test_viewer_cannot_create(self, make_member, running_experiment):
        from apps.organizations.models import Role

        viewer = make_member(Role.VIEWER)
        response = viewer.post(self.url(running_experiment), {"name": "x", "event_name": "y"}, format="json")
        assert response.status_code == 403


class TestGuardrailOnNamedMetric:
    def test_uses_metric_value(self):
        guardrail = Guardrail(name="Refunds", metric_name="Refund rate", source=GuardrailSource.CONVERSION,
                              operator=GuardrailOperator.RELATIVE_INCREASE_GT, threshold=20.0, is_active=True)
        metrics = [{"name": "Refund rate", "variants": {
            "control": {"users": 100, "value": 0.02}, "treatment": {"users": 100, "value": 0.03}}}]
        [r] = evaluate_guardrails([guardrail], {}, {}, metric_results=metrics)
        assert r["breached"] is True
        assert r["observed"] == pytest.approx(50.0)


@pytest.mark.django_db
def test_decision_includes_metric_evidence(authenticated_client, running_experiment, mock_clickhouse):
    ExperimentMetric.objects.create(experiment=running_experiment, name="Revenue", event_name="purchase",
                                    metric_type=MetricType.SECONDARY, aggregation=MetricAggregation.MEAN_VALUE)
    results = {
        "control": {"exposures": 1000, "unique_users": 1000, "conversions": 100, "conversion_rate": 0.1},
        "treatment": {"exposures": 1000, "unique_users": 1000, "conversions": 100, "conversion_rate": 0.1},
    }
    mock_clickhouse.query.return_value = MagicMock(result_rows=[
        ("control", 1000, 400, 5000.0, 125000.0), ("treatment", 1000, 450, 6000.0, 136000.0),
    ])
    with patch("apps.decisions.context.query_experiment_results", return_value=results), \
            patch("apps.decisions.context.query_variant_telemetry", return_value={}):
        response = authenticated_client.get(f"/api/v1/experiments/{running_experiment.id}/decision/")
    assert any(e["kind"] == "metric" and "Revenue" in e["statement"] for e in response.data["evidence"])
