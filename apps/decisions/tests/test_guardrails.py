import pytest

from apps.decisions.guardrails import evaluate_guardrails, summarize_for_health
from apps.decisions.models import Guardrail, GuardrailOperator, GuardrailSource

TELEMETRY = {
    "control": {"error_rate": {"count": 100, "avg": 1.2}, "latency_ms": {"count": 100, "avg": 100.0}},
    "treatment": {"error_rate": {"count": 100, "avg": 4.95}, "latency_ms": {"count": 100, "avg": 110.0}},
}

STATS = {
    "variants": {
        "control": {"unique_users": 1000, "conversion_rate": 0.10},
        "treatment": {"unique_users": 1000, "conversion_rate": 0.08},
    }
}


def g(**kwargs):
    defaults = {"name": "g", "metric_name": "error_rate", "source": GuardrailSource.TELEMETRY,
                "operator": GuardrailOperator.RELATIVE_INCREASE_GT, "threshold": 20.0, "is_active": True}
    defaults.update(kwargs)
    return Guardrail(**defaults)


class TestEvaluateGuardrails:
    def test_relative_increase_breach(self):
        [r] = evaluate_guardrails([g()], TELEMETRY, STATS)
        assert r["breached"] is True
        assert r["variant_key"] == "treatment"
        assert r["observed"] == pytest.approx(312.5)
        assert r["margin"] > 1

    def test_relative_increase_healthy(self):
        [r] = evaluate_guardrails([g(metric_name="latency_ms")], TELEMETRY, STATS)
        assert r["status"] == "healthy"
        assert r["observed"] == pytest.approx(10.0)

    def test_absolute_threshold(self):
        [r] = evaluate_guardrails([g(operator=GuardrailOperator.ABSOLUTE_GT, threshold=5.0)], TELEMETRY, STATS)
        assert r["breached"] is False
        [r] = evaluate_guardrails([g(operator=GuardrailOperator.ABSOLUTE_GT, threshold=4.0)], TELEMETRY, STATS)
        assert r["breached"] is True

    def test_absolute_lt(self):
        [r] = evaluate_guardrails(
            [g(metric_name="latency_ms", operator=GuardrailOperator.ABSOLUTE_LT, threshold=120)], TELEMETRY, STATS,
        )
        assert r["breached"] is True

    def test_conversion_decrease(self):
        guardrail = g(source=GuardrailSource.CONVERSION, metric_name="conversion_rate",
                      operator=GuardrailOperator.RELATIVE_DECREASE_GT, threshold=10.0)
        [r] = evaluate_guardrails([guardrail], TELEMETRY, STATS)
        assert r["observed"] == pytest.approx(-20.0)
        assert r["breached"] is True

    def test_missing_metric_is_no_data(self):
        [r] = evaluate_guardrails([g(metric_name="cpu")], TELEMETRY, STATS)
        assert r["status"] == "no_data"
        assert r["breached"] is False

    def test_inactive_skipped(self):
        assert evaluate_guardrails([g(is_active=False)], TELEMETRY, STATS) == []

    def test_summarize_for_health(self):
        results = evaluate_guardrails([g(name="errors"), g(name="latency", metric_name="latency_ms"),
                                       g(name="cpu", metric_name="cpu")], TELEMETRY, STATS)
        summary = summarize_for_health(results)
        assert {"name": "errors", "breached": True} in summary
        assert {"name": "latency", "breached": False} in summary
        assert all(s["name"] != "cpu" for s in summary)
