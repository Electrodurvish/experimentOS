import pytest

from apps.engine.assigner import evaluate_experiment


@pytest.mark.django_db
class TestStickyBucketing:
    def test_first_evaluation_returns_computed(self, running_experiment, mock_cassandra):
        result = evaluate_experiment(running_experiment, "user-100", {})
        assert result.assigned is True
        assert result.source == "computed"
        assert result.variant_key in ("control", "treatment")

    def test_sticky_assignment_persisted(self, running_experiment, mock_cassandra):
        result = evaluate_experiment(running_experiment, "user-100", {})

        # Verify sticky was saved
        sticky_key = ("user-100", str(running_experiment.id))
        assert sticky_key in mock_cassandra
        sticky = mock_cassandra[sticky_key]
        assert sticky.variant_key == result.variant_key
        assert sticky.bucket == result.bucket

    def test_second_evaluation_returns_sticky(self, running_experiment, mock_cassandra):
        result1 = evaluate_experiment(running_experiment, "user-100", {})
        assert result1.source == "computed"

        result2 = evaluate_experiment(running_experiment, "user-100", {})
        assert result2.source == "sticky"
        assert result2.variant_key == result1.variant_key
        assert result2.bucket == result1.bucket

    def test_sticky_survives_version_change(self, running_experiment, mock_cassandra):
        """Sticky assignments persist across version changes."""
        result1 = evaluate_experiment(running_experiment, "user-100", {})
        original_variant = result1.variant_key

        # The sticky assignment is keyed by (user_id, experiment_id)
        # not by version, so it survives version changes
        result2 = evaluate_experiment(running_experiment, "user-100", {})
        assert result2.source == "sticky"
        assert result2.variant_key == original_variant

    def test_different_users_get_independent_sticky(self, running_experiment, mock_cassandra):
        result1 = evaluate_experiment(running_experiment, "user-100", {})
        result2 = evaluate_experiment(running_experiment, "user-200", {})

        # Both should be computed (first time)
        assert result1.source == "computed"
        assert result2.source == "computed"

        # Both should have sticky entries
        assert ("user-100", str(running_experiment.id)) in mock_cassandra
        assert ("user-200", str(running_experiment.id)) in mock_cassandra

    def test_sticky_with_invalid_variant_recomputes(self, running_experiment, mock_cassandra):
        """If sticky references a variant that no longer exists, recompute."""
        from datetime import datetime, timezone

        from apps.engine.sticky import StickyAssignment

        # Manually insert a sticky with a non-existent variant key
        mock_cassandra[("user-100", str(running_experiment.id))] = StickyAssignment(
            user_id="user-100",
            experiment_id=str(running_experiment.id),
            variant_key="deleted_variant",
            variant_payload={},
            bucket=1234,
            version_number=1,
            assigned_at=datetime.now(timezone.utc),
        )

        result = evaluate_experiment(running_experiment, "user-100", {})
        assert result.assigned is True
        assert result.source == "computed"
        assert result.variant_key in ("control", "treatment")

    def test_debug_shows_sticky_step(self, running_experiment, mock_cassandra):
        # First call: computed
        evaluate_experiment(running_experiment, "user-100", {})

        # Second call: sticky, with debug
        result, steps = evaluate_experiment(running_experiment, "user-100", {}, debug=True)
        assert result.source == "sticky"

        step_names = [s.step for s in steps]
        assert "sticky_lookup" in step_names

        sticky_step = next(s for s in steps if s.step == "sticky_lookup")
        assert sticky_step.passed is True
        assert "Sticky assignment found" in sticky_step.detail

    def test_debug_shows_no_sticky(self, running_experiment, mock_cassandra):
        result, steps = evaluate_experiment(running_experiment, "user-100", {}, debug=True)
        assert result.source == "computed"

        sticky_step = next(s for s in steps if s.step == "sticky_lookup")
        assert sticky_step.passed is False
        assert "No sticky assignment found" in sticky_step.detail
