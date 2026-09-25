from unittest.mock import patch

import pytest

from apps.audit.models import AuditLog
from apps.decisions.engine import DecisionResult
from apps.decisions.models import Recommendation, RolloutAction, RolloutChange
from apps.decisions.rollout import apply_decision, change_rollout
from apps.engine.assigner import evaluate_experiment
from apps.engine.hasher import compute_rollout_bucket
from apps.experiments.models import ExperimentStatus
from apps.intelligence.models import TimelineEvent, TimelineEventType


def _result(recommendation, target=None):
    return DecisionResult(recommendation=recommendation, confidence=0.9, confidence_label="HIGH",
                          summary="because", target_percentage=target)


@pytest.mark.django_db
class TestRolloutGate:
    def test_users_outside_rollout_are_excluded(self, running_experiment, mock_cassandra):
        running_experiment.rollout_percentage = 1000
        running_experiment.save()
        users = [f"user-{i}" for i in range(400)]
        results = {u: evaluate_experiment(running_experiment, u, {}) for u in users}
        for user, result in results.items():
            inside = compute_rollout_bucket(user, running_experiment.key) < 1000
            assert result.assigned is inside
            if not inside:
                assert result.reason == "rollout_excluded"
        assigned = sum(r.assigned for r in results.values())
        assert 20 < assigned < 70  # ~10% of 400

    def test_rollback_keeps_original_cohort(self, running_experiment, mock_cassandra):
        users = [f"u{i}" for i in range(300)]
        running_experiment.rollout_percentage = 5000
        running_experiment.save()
        at_50 = {u for u in users if evaluate_experiment(running_experiment, u, {}).assigned}
        running_experiment.rollout_percentage = 1000
        running_experiment.save()
        at_10 = {u for u in users if evaluate_experiment(running_experiment, u, {}).assigned}
        assert at_10 and at_10 < at_50  # monotonic, and sticky users outside the rollout are dropped

    def test_debug_step(self, running_experiment, mock_cassandra):
        running_experiment.rollout_percentage = 0
        running_experiment.save()
        result, steps = evaluate_experiment(running_experiment, "u1", {}, debug=True)
        assert result.reason == "rollout_excluded"
        assert steps[-1].step == "rollout_check"


@pytest.mark.django_db
class TestChangeRollout:
    def test_records_history_audit_and_timeline(self, running_experiment, user):
        change = change_rollout(running_experiment, 2500, RolloutAction.MANUAL, "ramp", actor=user)
        running_experiment.refresh_from_db()
        assert running_experiment.rollout_percentage == 2500
        assert change.from_percentage == 10000 and change.to_percentage == 2500
        assert AuditLog.objects.filter(experiment=running_experiment, action="rollout_changed").exists()
        assert TimelineEvent.objects.filter(experiment=running_experiment,
                                            event_type=TimelineEventType.ROLLOUT_CHANGED).exists()

    def test_rollback_event_shape(self, running_experiment):
        change = change_rollout(running_experiment, 1000, RolloutAction.ROLLBACK, "error_rate_guardrail",
                                automated=True)
        event = TimelineEvent.objects.get(event_type=TimelineEventType.ROLLBACK_TRIGGERED)
        assert event.metadata["action"] == "rollback"
        assert event.metadata["from"] == 100 and event.metadata["to"] == 10
        assert event.metadata["reason"] == "error_rate_guardrail"
        assert AuditLog.objects.filter(action="rollback_triggered").exists()
        assert change.automated

    def test_noop_when_unchanged(self, running_experiment):
        assert change_rollout(running_experiment, 10000, RolloutAction.MANUAL, "same") is None
        assert RolloutChange.objects.count() == 0

    def test_invalidates_cache(self, running_experiment):
        with patch("apps.decisions.rollout.invalidate_experiment_config") as invalidate:
            change_rollout(running_experiment, 5000, RolloutAction.MANUAL, "x")
        invalidate.assert_called_once_with(str(running_experiment.project_id), running_experiment.key)


@pytest.mark.django_db
class TestApplyDecision:
    def test_rollback(self, running_experiment):
        applied = apply_decision(running_experiment, _result(Recommendation.ROLLBACK, 1000))
        assert applied == {"action": "rollback", "from": 10000, "to": 1000}

    def test_pause_transitions_state(self, running_experiment):
        applied = apply_decision(running_experiment, _result(Recommendation.PAUSE))
        running_experiment.refresh_from_db()
        assert applied["action"] == "pause"
        assert running_experiment.status == ExperimentStatus.PAUSED
        assert TimelineEvent.objects.filter(event_type=TimelineEventType.EXPERIMENT_PAUSED).exists()

    def test_complete_and_continue_do_nothing(self, running_experiment):
        assert apply_decision(running_experiment, _result(Recommendation.COMPLETE)) is None
        assert apply_decision(running_experiment, _result(Recommendation.CONTINUE)) is None
