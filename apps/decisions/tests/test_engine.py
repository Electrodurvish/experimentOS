from apps.decisions.engine import decide, harmful_anomalies, next_stage, previous_stage
from apps.decisions.models import Recommendation


def stats(lift=0.12, p_value=0.001, significant=True, users=50000, needed=30000, srm=False):
    return {
        "variants": {
            "control": {"unique_users": users, "conversion_rate": 0.10},
            "treatment": {
                "unique_users": users, "conversion_rate": 0.10 * (1 + lift),
                "lift": lift, "p_value": p_value, "is_significant": significant,
            },
        },
        "srm": {"p_value": 0.0001 if srm else 0.6, "is_mismatch": srm, "observed_counts": {}},
        "sample_size": {"recommended_per_variant": needed},
    }


def inputs(**overrides):
    base = {
        "status": "RUNNING",
        "rollout_percentage": 2500,
        "policy": {"stages": [1000, 2500, 5000, 10000], "rollback_percentage": 1000, "min_health_score": 70},
        "control_key": "control",
        "stats": stats(),
        "health": {"overall_score": 92, "dimensions": {}},
        "guardrails": [],
        "production_impact": {},
        "anomalies": [],
        "segments": None,
        "interactions": [],
    }
    base.update(overrides)
    return base


def breach(action="ROLLBACK", margin=2.0):
    return {"guardrail_id": "g1", "name": "Error rate", "metric_name": "error_rate", "variant_key": "treatment",
            "observed": 312.0, "threshold": 20.0, "operator": "RELATIVE_INCREASE_GT", "action": action,
            "breached": True, "margin": margin, "status": "breached"}


class TestStages:
    def test_next_and_previous(self):
        stages = [1000, 2500, 5000, 10000]
        assert next_stage(stages, 2500) == 5000
        assert next_stage(stages, 10000) is None
        assert next_stage(stages, 3000) == 5000
        assert previous_stage(stages, 5000) == 2500
        assert previous_stage(stages, 1000) is None


class TestDecide:
    def test_increase_rollout_when_everything_healthy(self):
        result = decide(inputs())
        assert result.recommendation == Recommendation.INCREASE_ROLLOUT
        assert result.target_percentage == 5000
        assert result.confidence_label == "HIGH"
        assert all(c["passed"] for c in result.checks)
        assert any(e["kind"] == "primary_metric" for e in result.evidence)

    def test_complete_at_full_rollout(self):
        result = decide(inputs(rollout_percentage=10000))
        assert result.recommendation == Recommendation.COMPLETE
        assert result.target_percentage is None

    def test_guardrail_rollback(self):
        result = decide(inputs(rollout_percentage=5000, guardrails=[breach()]))
        assert result.recommendation == Recommendation.ROLLBACK
        assert result.target_percentage == 1000
        assert result.confidence_label == "HIGH"
        assert "Error rate" in result.evidence[0]["statement"] or any(
            e["kind"] == "guardrail" for e in result.evidence
        )

    def test_guardrail_at_floor_pauses(self):
        result = decide(inputs(rollout_percentage=1000, guardrails=[breach()]))
        assert result.recommendation == Recommendation.PAUSE

    def test_guardrail_pause_action(self):
        result = decide(inputs(guardrails=[breach(action="PAUSE")]))
        assert result.recommendation == Recommendation.PAUSE

    def test_critical_anomaly_decreases(self):
        anomaly = {"variant_key": "treatment", "metric_name": "error_rate", "timestamp": "t", "value": 5.8,
                   "baseline_mean": 1.4, "z_score": None, "severity": "critical"}
        result = decide(inputs(rollout_percentage=5000, anomalies=[anomaly]))
        assert result.recommendation == Recommendation.DECREASE_ROLLOUT
        assert result.target_percentage == 2500

    def test_srm_pauses(self):
        result = decide(inputs(stats=stats(srm=True)))
        assert result.recommendation == Recommendation.PAUSE
        assert not next(c for c in result.checks if c["name"] == "srm_not_detected")["passed"]

    def test_significant_regression_rolls_back(self):
        result = decide(inputs(stats=stats(lift=-0.08, p_value=0.002)))
        assert result.recommendation == Recommendation.ROLLBACK
        assert result.target_percentage == 1000

    def test_production_critical_decreases(self):
        impact = {"treatment": {"latency_ms": {"control_avg": 100, "variant_avg": 143, "change_pct": 43.0,
                                               "status": "critical"}}}
        result = decide(inputs(rollout_percentage=5000, production_impact=impact))
        assert result.recommendation == Recommendation.DECREASE_ROLLOUT
        assert any(e["kind"] == "production" for e in result.evidence)

    def test_low_health_holds(self):
        result = decide(inputs(health={"overall_score": 60, "dimensions": {}}))
        assert result.recommendation == Recommendation.CONTINUE

    def test_critical_health_pauses(self):
        result = decide(inputs(health={"overall_score": 30, "dimensions": {}}))
        assert result.recommendation == Recommendation.PAUSE

    def test_insufficient_sample_continues(self):
        result = decide(inputs(stats=stats(users=1000, needed=30000)))
        assert result.recommendation == Recommendation.CONTINUE
        assert "Sufficient sample size" in result.summary

    def test_not_significant_continues(self):
        result = decide(inputs(stats=stats(lift=0.02, p_value=0.3, significant=False)))
        assert result.recommendation == Recommendation.CONTINUE

    def test_segment_regression_blocks_increase(self):
        segments = {"segments": [{"dimension": "platform", "value": "android", "lift": -0.2, "p_value": 0.001,
                                  "is_significant": True}], "top_contributors": []}
        result = decide(inputs(segments=segments))
        assert result.recommendation == Recommendation.CONTINUE
        assert any(e["kind"] == "segment" for e in result.evidence)

    def test_interaction_blocks_increase(self):
        interaction = {"experiment_a": "a", "experiment_b": "b", "interaction_type": "antagonistic",
                       "interaction_effect": -0.03, "is_interaction": True}
        result = decide(inputs(interactions=[interaction]))
        assert result.recommendation == Recommendation.CONTINUE

    def test_not_running(self):
        result = decide(inputs(status="PAUSED", guardrails=[breach()]))
        assert result.recommendation == Recommendation.CONTINUE
        assert "PAUSED" in result.summary

    def test_evidence_ids_are_sequential(self):
        result = decide(inputs(guardrails=[breach()]))
        assert [e["id"] for e in result.evidence] == [f"E{i + 1}" for i in range(len(result.evidence))]


class TestHarmfulAnomalies:
    def test_filters_control_and_direction(self):
        up = {"timestamp": "t", "value": 5.0, "baseline_mean": 1.0, "z_score": 6.0, "severity": "critical"}
        down = {"timestamp": "t", "value": 0.1, "baseline_mean": 1.0, "z_score": -6.0, "severity": "critical"}
        result = harmful_anomalies({
            "error_rate": {"control": [up], "treatment": [up, down]},
            "throughput_rps": {"treatment": [up, down]},
        })
        assert [(a["metric_name"], a["value"]) for a in result] == [("error_rate", 5.0), ("throughput_rps", 0.1)]
