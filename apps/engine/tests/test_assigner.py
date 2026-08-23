import pytest

from apps.engine.assigner import evaluate_experiment
from apps.engine.models import Assignment
from apps.experiments.models import ExperimentStatus


@pytest.mark.django_db
class TestEvaluateExperiment:
    def test_assigns_variant(self, running_experiment):
        result = evaluate_experiment(
            experiment=running_experiment,
            user_id="user-123",
            context={},
        )
        assert result.assigned is True
        assert result.variant_key in ("control", "treatment")
        assert 0 <= result.bucket < 10000
        assert result.version_number == 1
        assert result.reason == "assigned"

    def test_deterministic_assignment(self, running_experiment):
        result1 = evaluate_experiment(running_experiment, "user-123", {})
        result2 = evaluate_experiment(running_experiment, "user-123", {})
        assert result1.variant_key == result2.variant_key
        assert result1.bucket == result2.bucket

    def test_not_running_experiment(self, running_experiment):
        running_experiment.status = ExperimentStatus.DRAFT
        running_experiment.save()
        result = evaluate_experiment(running_experiment, "user-123", {})
        assert result.assigned is False
        assert result.reason == "experiment_not_running"

    def test_no_active_version(self, running_experiment):
        version = running_experiment.current_version
        version.is_active = False
        version.save(update_fields=["is_active"])
        result = evaluate_experiment(running_experiment, "user-123", {})
        assert result.assigned is False
        assert result.reason == "no_active_version"

    def test_targeting_excludes_user(self, running_experiment):
        from conftest import TargetingRuleFactory

        TargetingRuleFactory(
            version=running_experiment.current_version,
            rules_json={
                "operator": "AND",
                "conditions": [
                    {"field": "user.country", "operator": "equals", "value": "IN"},
                ],
            },
        )
        result = evaluate_experiment(
            running_experiment, "user-123", {"user": {"country": "US"}}
        )
        assert result.assigned is False
        assert result.reason == "not_targeted"

    def test_targeting_includes_user(self, running_experiment):
        from conftest import TargetingRuleFactory

        TargetingRuleFactory(
            version=running_experiment.current_version,
            rules_json={
                "operator": "AND",
                "conditions": [
                    {"field": "user.country", "operator": "equals", "value": "IN"},
                ],
            },
        )
        result = evaluate_experiment(
            running_experiment, "user-123", {"user": {"country": "IN"}}
        )
        assert result.assigned is True

    def test_creates_assignment_record(self, running_experiment):
        evaluate_experiment(running_experiment, "user-456", {})
        assignment = Assignment.objects.get(
            user_id="user-456", experiment=running_experiment
        )
        assert assignment.bucket is not None
        assert assignment.variant is not None

    def test_debug_mode_returns_steps(self, running_experiment):
        result, steps = evaluate_experiment(
            running_experiment, "user-123", {}, debug=True
        )
        assert result.assigned is True
        assert len(steps) >= 4  # status, version, targeting, bucket, traffic, variant
        step_names = [s.step for s in steps]
        assert "status_check" in step_names
        assert "bucket_computation" in step_names
        assert "variant_assignment" in step_names

    def test_traffic_exclusion(self, running_experiment):
        # Set traffic allocation to 1 (only bucket 0 gets through)
        version = running_experiment.current_version
        version.traffic_allocation = 1
        version.is_locked = False
        version.save(update_fields=["traffic_allocation", "is_locked"])

        # Most users will be excluded
        excluded_count = 0
        for i in range(100):
            result = evaluate_experiment(running_experiment, f"user-{i}", {})
            if not result.assigned and result.reason == "traffic_excluded":
                excluded_count += 1
        # With allocation of 1/10000, almost all should be excluded
        assert excluded_count > 95
