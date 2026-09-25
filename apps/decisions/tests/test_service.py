from datetime import timedelta
from unittest.mock import MagicMock, patch

import pytest
from django.utils import timezone

from apps.decisions.models import (
    Decision,
    Guardrail,
    GuardrailOperator,
    Recommendation,
    RolloutPolicy,
)
from apps.decisions.service import run_decision
from apps.decisions.tasks import evaluate_running_experiments, recalculate_health_scores, send_alert
from apps.experiments.models import ExperimentStatus
from apps.intelligence.models import TimelineEvent, TimelineEventType

RESULTS = {
    "control": {"exposures": 70000, "unique_users": 60000, "conversions": 6000, "conversion_rate": 0.10},
    "treatment": {"exposures": 70000, "unique_users": 60000, "conversions": 7200, "conversion_rate": 0.12},
}

TELEMETRY_ROWS = [
    ("control", "error_rate", 1000, 1.2, 1.2, 1.5, 1.6, 0.5, 2.0),
    ("treatment", "error_rate", 1000, 4.95, 4.9, 6.0, 7.0, 2.0, 9.0),
]


@pytest.fixture
def results():
    with patch("apps.decisions.context.query_experiment_results", return_value=RESULTS) as m:
        yield m


@pytest.fixture
def policy(running_experiment):
    running_experiment.rollout_percentage = 2500
    running_experiment.started_at = timezone.now() - timedelta(days=1)
    running_experiment.save()
    return RolloutPolicy.objects.create(experiment=running_experiment, auto_advance=True, min_confidence=0.8)


def _error_guardrail(experiment):
    return Guardrail.objects.create(experiment=experiment, name="Error rate", metric_name="error_rate",
                                    operator=GuardrailOperator.RELATIVE_INCREASE_GT, threshold=20.0)


@pytest.mark.django_db
class TestRunDecision:
    def test_persists_without_applying(self, running_experiment, results):
        decision, applied = run_decision(running_experiment)
        assert applied is None
        assert Decision.objects.filter(experiment=running_experiment).count() == 1
        assert decision.recommendation == Recommendation.COMPLETE  # 100% rollout, clear winner
        assert decision.inputs["health_score"] is not None

    def test_manual_apply_increases_rollout(self, running_experiment, results, policy):
        decision, applied = run_decision(running_experiment, apply=True)
        running_experiment.refresh_from_db()
        assert decision.recommendation == Recommendation.INCREASE_ROLLOUT
        assert applied == {"action": "increase", "from": 2500, "to": 5000}
        assert running_experiment.rollout_percentage == 5000
        assert TimelineEvent.objects.filter(event_type=TimelineEventType.DECISION_MADE).exists()

    def test_automated_rollback_on_guardrail(self, running_experiment, results, policy, mock_clickhouse):
        _error_guardrail(running_experiment)
        mock_clickhouse.query.return_value = MagicMock(result_rows=TELEMETRY_ROWS)
        with patch("apps.decisions.tasks.send_alert.delay") as alert:
            decision, applied = run_decision(running_experiment, apply=True, automated=True)
        running_experiment.refresh_from_db()
        assert decision.recommendation == Recommendation.ROLLBACK
        assert running_experiment.rollout_percentage == 1000
        assert decision.applied_action == "rollback"
        assert decision.triggered_by == "scheduler"
        alert.assert_called_once()

    def test_automation_requires_policy(self, running_experiment, results):
        running_experiment.rollout_percentage = 2500
        running_experiment.save()
        _, applied = run_decision(running_experiment, apply=True, automated=True)
        assert applied is None

    def test_auto_advance_disabled(self, running_experiment, results, policy):
        policy.auto_advance = False
        policy.save()
        _, applied = run_decision(running_experiment, apply=True, automated=True)
        assert applied is None

    def test_min_stage_duration(self, running_experiment, results, policy):
        policy.min_stage_duration_minutes = 60 * 48
        policy.save()
        _, applied = run_decision(running_experiment, apply=True, automated=True)
        assert applied is None

    def test_auto_rollback_disabled(self, running_experiment, results, policy, mock_clickhouse):
        policy.auto_rollback = False
        policy.save()
        _error_guardrail(running_experiment)
        mock_clickhouse.query.return_value = MagicMock(result_rows=TELEMETRY_ROWS)
        decision, applied = run_decision(running_experiment, apply=True, automated=True)
        assert decision.recommendation == Recommendation.ROLLBACK
        assert applied is None


@pytest.mark.django_db
class TestTasks:
    def test_evaluate_running_experiments(self, running_experiment, results, policy):
        summary = evaluate_running_experiments()
        assert summary == {"evaluated": 1, "applied": 1, "failed": 0}

    def test_evaluate_skips_non_running(self, running_experiment, results):
        running_experiment.status = ExperimentStatus.PAUSED
        running_experiment.save()
        assert evaluate_running_experiments()["evaluated"] == 0

    def test_failures_are_isolated(self, running_experiment):
        with patch("apps.decisions.service.gather_inputs", side_effect=RuntimeError):
            assert evaluate_running_experiments()["failed"] == 1

    def test_recalculate_health_records_once(self, running_experiment, results):
        assert recalculate_health_scores() == {"recorded": 1}
        assert recalculate_health_scores() == {"recorded": 0}

    def test_send_alert_without_webhook(self, running_experiment, settings):
        settings.ALERT_WEBHOOK_URL = ""
        assert send_alert(str(running_experiment.id), "rolled back") is False

    def test_send_alert_posts_webhook(self, running_experiment, settings):
        settings.ALERT_WEBHOOK_URL = "https://hooks.example.com/x"
        with patch("urllib.request.urlopen") as urlopen:
            assert send_alert(str(running_experiment.id), "rolled back", "critical") is True
        request = urlopen.call_args.args[0]
        assert b"test-experiment" in request.data
