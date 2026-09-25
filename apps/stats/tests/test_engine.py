
from apps.stats.engine import (
    is_significant,
    relative_lift,
    required_sample_size,
    srm_test,
    two_proportion_z_test,
    wilson_confidence_interval,
)


class TestWilsonConfidenceInterval:
    def test_basic_ci(self):
        lower, upper = wilson_confidence_interval(100, 1000)
        assert 0.08 < lower < 0.10
        assert 0.10 < upper < 0.13

    def test_rate_within_ci(self):
        lower, upper = wilson_confidence_interval(500, 5000)
        rate = 500 / 5000
        assert lower < rate < upper

    def test_zero_conversions(self):
        lower, upper = wilson_confidence_interval(0, 1000)
        assert lower == 0.0
        assert upper > 0.0

    def test_all_conversions(self):
        lower, upper = wilson_confidence_interval(1000, 1000)
        assert lower < 1.0
        assert upper == 1.0

    def test_zero_total(self):
        lower, upper = wilson_confidence_interval(0, 0)
        assert lower == 0.0
        assert upper == 0.0

    def test_wider_ci_for_lower_confidence(self):
        lower_95, upper_95 = wilson_confidence_interval(100, 1000, confidence=0.95)
        lower_99, upper_99 = wilson_confidence_interval(100, 1000, confidence=0.99)
        # 99% CI should be wider than 95%
        assert (upper_99 - lower_99) > (upper_95 - lower_95)


class TestTwoProportionZTest:
    def test_identical_proportions(self):
        z, p = two_proportion_z_test(100, 1000, 100, 1000)
        assert z == 0.0
        assert p == 1.0

    def test_significantly_different(self):
        # 10% vs 12% with large sample — should be significant
        z, p = two_proportion_z_test(5000, 50000, 6000, 50000)
        assert p < 0.05
        assert z > 0

    def test_not_significant_small_sample(self):
        # Same rates but very small sample
        z, p = two_proportion_z_test(1, 10, 2, 10)
        assert p > 0.05

    def test_zero_total(self):
        z, p = two_proportion_z_test(0, 0, 0, 0)
        assert z == 0.0
        assert p == 1.0

    def test_negative_lift_detected(self):
        # Treatment worse than control
        z, p = two_proportion_z_test(6000, 50000, 5000, 50000)
        assert z < 0
        assert p < 0.05


class TestRelativeLift:
    def test_positive_lift(self):
        result = relative_lift(1000, 10000, 1200, 10000)
        assert result["lift"] > 0
        assert result["absolute_difference"] > 0

    def test_no_lift(self):
        result = relative_lift(1000, 10000, 1000, 10000)
        assert result["lift"] == 0.0
        assert result["absolute_difference"] == 0.0

    def test_negative_lift(self):
        result = relative_lift(1200, 10000, 1000, 10000)
        assert result["lift"] < 0
        assert result["absolute_difference"] < 0

    def test_ci_contains_lift(self):
        result = relative_lift(5000, 50000, 6000, 50000)
        assert result["lift_ci_lower"] < result["lift"] < result["lift_ci_upper"]

    def test_zero_control(self):
        result = relative_lift(0, 10000, 100, 10000)
        assert result["lift"] == float("inf")

    def test_zero_total(self):
        result = relative_lift(0, 0, 0, 0)
        assert result["lift"] == 0.0

    def test_20_percent_lift(self):
        # 10% control, 12% treatment = 20% relative lift
        result = relative_lift(1000, 10000, 1200, 10000)
        assert abs(result["lift"] - 0.20) < 0.001


class TestSRMTest:
    def test_balanced_samples(self):
        chi2, p = srm_test([50000, 50000])
        assert chi2 == 0.0
        assert p == 1.0

    def test_slight_imbalance_not_significant(self):
        chi2, p = srm_test([5010, 4990])
        assert p > 0.01

    def test_severe_imbalance_detected(self):
        chi2, p = srm_test([63000, 37000])
        assert p < 0.01

    def test_three_variants_balanced(self):
        chi2, p = srm_test([33333, 33333, 33334])
        assert p > 0.01

    def test_three_variants_imbalanced(self):
        chi2, p = srm_test([50000, 30000, 20000])
        assert p < 0.01

    def test_custom_expected_proportions(self):
        # 70/30 split, observed matches
        chi2, p = srm_test([7000, 3000], [0.7, 0.3])
        assert p > 0.01

    def test_single_variant(self):
        chi2, p = srm_test([1000])
        assert chi2 == 0.0
        assert p == 1.0

    def test_empty_counts(self):
        chi2, p = srm_test([0, 0])
        assert p == 1.0


class TestRequiredSampleSize:
    def test_basic_calculation(self):
        n = required_sample_size(0.10, 0.01)
        # For 10% baseline, 1% MDE, ~14000-15000 per variant
        assert 10000 < n < 20000

    def test_smaller_mde_needs_more(self):
        n1 = required_sample_size(0.10, 0.02)
        n2 = required_sample_size(0.10, 0.01)
        assert n2 > n1

    def test_higher_power_needs_more(self):
        n1 = required_sample_size(0.10, 0.01, power=0.80)
        n2 = required_sample_size(0.10, 0.01, power=0.95)
        assert n2 > n1

    def test_zero_baseline(self):
        n = required_sample_size(0.0, 0.01)
        assert n == 0

    def test_zero_mde(self):
        n = required_sample_size(0.10, 0.0)
        assert n == 0


class TestIsSignificant:
    def test_significant(self):
        assert is_significant(0.01) is True

    def test_not_significant(self):
        assert is_significant(0.10) is False

    def test_boundary(self):
        assert is_significant(0.05) is False
        assert is_significant(0.049) is True
