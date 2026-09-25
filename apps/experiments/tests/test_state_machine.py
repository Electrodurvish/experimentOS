import pytest
from django.core.exceptions import ValidationError

from apps.common.exceptions import InvalidTransitionError
from apps.experiments.models import ExperimentStatus
from apps.experiments.state_machine import VALID_TRANSITIONS, ExperimentStateMachine
from conftest import (
    ExperimentFactory,
    ExperimentVersionFactory,
    UserFactory,
    VariantFactory,
)


@pytest.mark.django_db
class TestExperimentStateMachine:
    def _make_startable_experiment(self):
        """Create a DRAFT experiment that can be transitioned to RUNNING."""
        experiment = ExperimentFactory(status=ExperimentStatus.DRAFT)
        version = ExperimentVersionFactory(experiment=experiment, version_number=1)
        VariantFactory(
            version=version, key="control", is_control=True,
            traffic_percentage=5000, bucket_start=0, bucket_end=4999,
        )
        VariantFactory(
            version=version, key="treatment", is_control=False,
            traffic_percentage=5000, bucket_start=5000, bucket_end=9999,
        )
        experiment.current_version = version
        experiment.save()
        return experiment

    def test_valid_transition_draft_to_review(self):
        experiment = ExperimentFactory(status=ExperimentStatus.DRAFT)
        sm = ExperimentStateMachine(experiment)
        actor = UserFactory()
        result = sm.transition_to(ExperimentStatus.REVIEW, actor=actor)
        assert result.status == ExperimentStatus.RUNNING and False or result.status == ExperimentStatus.REVIEW

    def test_valid_transition_draft_to_review_simple(self):
        experiment = ExperimentFactory(status=ExperimentStatus.DRAFT)
        sm = ExperimentStateMachine(experiment)
        result = sm.transition_to(ExperimentStatus.REVIEW)
        assert result.status == ExperimentStatus.REVIEW

    def test_invalid_transition_draft_to_running(self):
        experiment = ExperimentFactory(status=ExperimentStatus.DRAFT)
        sm = ExperimentStateMachine(experiment)
        with pytest.raises(InvalidTransitionError, match="Cannot transition"):
            sm.transition_to(ExperimentStatus.RUNNING)

    def test_all_valid_transitions(self):
        for from_status, to_statuses in VALID_TRANSITIONS.items():
            for to_status in to_statuses:
                if to_status == ExperimentStatus.RUNNING:
                    experiment = self._make_startable_experiment()
                    # Move through required states
                    sm = ExperimentStateMachine(experiment)
                    if from_status == ExperimentStatus.APPROVED:
                        sm.transition_to(ExperimentStatus.REVIEW)
                        sm.transition_to(ExperimentStatus.APPROVED)
                    elif from_status == ExperimentStatus.PAUSED:
                        sm.transition_to(ExperimentStatus.REVIEW)
                        sm.transition_to(ExperimentStatus.APPROVED)
                        sm.transition_to(ExperimentStatus.RUNNING)
                        sm.transition_to(ExperimentStatus.PAUSED)
                    sm.transition_to(to_status)
                    assert experiment.status == to_status
                else:
                    experiment = ExperimentFactory(status=from_status)
                    if to_status in (ExperimentStatus.COMPLETED, ExperimentStatus.ARCHIVED):
                        # Need a current version
                        version = ExperimentVersionFactory(experiment=experiment)
                        experiment.current_version = version
                        experiment.save()
                    sm = ExperimentStateMachine(experiment)
                    sm.transition_to(to_status)
                    assert experiment.status == to_status

    def test_all_invalid_transitions(self):
        all_statuses = set(ExperimentStatus)
        for from_status, valid_targets in VALID_TRANSITIONS.items():
            invalid_targets = all_statuses - set(valid_targets) - {from_status}
            for to_status in invalid_targets:
                experiment = ExperimentFactory(status=from_status)
                sm = ExperimentStateMachine(experiment)
                with pytest.raises(InvalidTransitionError):
                    sm.transition_to(to_status)

    def test_start_locks_version(self):
        experiment = self._make_startable_experiment()
        sm = ExperimentStateMachine(experiment)
        sm.transition_to(ExperimentStatus.REVIEW)
        sm.transition_to(ExperimentStatus.APPROVED)
        sm.transition_to(ExperimentStatus.RUNNING)
        experiment.current_version.refresh_from_db()
        assert experiment.current_version.is_locked is True
        assert experiment.current_version.is_active is True

    def test_start_sets_started_at(self):
        experiment = self._make_startable_experiment()
        assert experiment.started_at is None
        sm = ExperimentStateMachine(experiment)
        sm.transition_to(ExperimentStatus.REVIEW)
        sm.transition_to(ExperimentStatus.APPROVED)
        sm.transition_to(ExperimentStatus.RUNNING)
        assert experiment.started_at is not None

    def test_complete_sets_ended_at(self):
        experiment = self._make_startable_experiment()
        sm = ExperimentStateMachine(experiment)
        sm.transition_to(ExperimentStatus.REVIEW)
        sm.transition_to(ExperimentStatus.APPROVED)
        sm.transition_to(ExperimentStatus.RUNNING)
        sm.transition_to(ExperimentStatus.COMPLETED)
        assert experiment.ended_at is not None

    def test_complete_deactivates_version(self):
        experiment = self._make_startable_experiment()
        sm = ExperimentStateMachine(experiment)
        sm.transition_to(ExperimentStatus.REVIEW)
        sm.transition_to(ExperimentStatus.APPROVED)
        sm.transition_to(ExperimentStatus.RUNNING)
        sm.transition_to(ExperimentStatus.COMPLETED)
        experiment.current_version.refresh_from_db()
        assert experiment.current_version.is_active is False

    def test_cannot_start_without_version(self):
        experiment = ExperimentFactory(status=ExperimentStatus.APPROVED)
        sm = ExperimentStateMachine(experiment)
        with pytest.raises(ValidationError, match="no current version"):
            sm.transition_to(ExperimentStatus.RUNNING)

    def test_cannot_start_with_one_variant(self):
        experiment = ExperimentFactory(status=ExperimentStatus.APPROVED)
        version = ExperimentVersionFactory(experiment=experiment)
        VariantFactory(version=version, key="control", is_control=True)
        experiment.current_version = version
        experiment.save()
        sm = ExperimentStateMachine(experiment)
        with pytest.raises(ValidationError, match="at least 2 variants"):
            sm.transition_to(ExperimentStatus.RUNNING)

    def test_cannot_start_without_control(self):
        experiment = ExperimentFactory(status=ExperimentStatus.APPROVED)
        version = ExperimentVersionFactory(experiment=experiment)
        VariantFactory(version=version, key="a", is_control=False,
                      traffic_percentage=5000, bucket_start=0, bucket_end=4999)
        VariantFactory(version=version, key="b", is_control=False,
                      traffic_percentage=5000, bucket_start=5000, bucket_end=9999)
        experiment.current_version = version
        experiment.save()
        sm = ExperimentStateMachine(experiment)
        with pytest.raises(ValidationError, match="exactly 1 control"):
            sm.transition_to(ExperimentStatus.RUNNING)

    def test_get_allowed_transitions(self):
        experiment = ExperimentFactory(status=ExperimentStatus.DRAFT)
        sm = ExperimentStateMachine(experiment)
        allowed = sm.get_allowed_transitions()
        assert ExperimentStatus.REVIEW in allowed
        assert ExperimentStatus.ARCHIVED in allowed
        assert ExperimentStatus.RUNNING not in allowed

    def test_creates_audit_log(self):
        from apps.audit.models import AuditLog

        experiment = ExperimentFactory(status=ExperimentStatus.DRAFT)
        actor = UserFactory()
        sm = ExperimentStateMachine(experiment)
        sm.transition_to(ExperimentStatus.REVIEW, actor=actor)

        log = AuditLog.objects.get(experiment=experiment, action="STATUS_CHANGED")
        assert log.organization_id == experiment.project.organization_id
        assert log.old_value == {"status": "DRAFT"}
        assert log.new_value == {"status": "REVIEW"}
        assert log.actor == actor
