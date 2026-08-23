from apps.stats.analyzer import analyze_experiment


class TestAnalyzeExperiment:
    def test_empty_data(self):
        result = analyze_experiment({})
        assert result["variants"] == {}
        assert result["srm"] is None
        assert result["sample_size"] is None

    def test_basic_analysis(self):
        variant_data = {
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

        result = analyze_experiment(variant_data)

        # Control should have CI but no lift/p-value
        control = result["variants"]["control"]
        assert control["ci_lower"] > 0
        assert control["ci_upper"] > control["ci_lower"]
        assert "lift" not in control

        # Treatment should have lift and p-value
        treatment = result["variants"]["treatment"]
        assert treatment["lift"] > 0
        assert treatment["p_value"] < 0.05
        assert treatment["is_significant"] is True
        assert treatment["ci_lower"] > 0
        assert treatment["ci_upper"] > treatment["ci_lower"]
        assert treatment["absolute_difference"] > 0

    def test_no_significant_difference(self):
        variant_data = {
            "control": {
                "exposures": 200,
                "unique_users": 100,
                "conversions": 10,
                "conversion_rate": 0.10,
            },
            "treatment": {
                "exposures": 200,
                "unique_users": 100,
                "conversions": 11,
                "conversion_rate": 0.11,
            },
        }

        result = analyze_experiment(variant_data)
        treatment = result["variants"]["treatment"]
        assert treatment["is_significant"] is False

    def test_srm_balanced(self):
        variant_data = {
            "control": {
                "exposures": 100000,
                "unique_users": 50000,
                "conversions": 5000,
                "conversion_rate": 0.10,
            },
            "treatment": {
                "exposures": 100000,
                "unique_users": 50000,
                "conversions": 5000,
                "conversion_rate": 0.10,
            },
        }

        result = analyze_experiment(variant_data)
        assert result["srm"]["is_mismatch"] is False

    def test_srm_imbalanced(self):
        variant_data = {
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

        result = analyze_experiment(variant_data)
        assert result["srm"]["is_mismatch"] is True

    def test_sample_size_recommendation(self):
        variant_data = {
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

        result = analyze_experiment(variant_data)
        assert result["sample_size"]["recommended_per_variant"] > 0
        assert result["sample_size"]["baseline_rate"] == 0.1

    def test_three_variants(self):
        variant_data = {
            "control": {
                "exposures": 90000,
                "unique_users": 30000,
                "conversions": 3000,
                "conversion_rate": 0.10,
            },
            "treatment_a": {
                "exposures": 90000,
                "unique_users": 30000,
                "conversions": 3600,
                "conversion_rate": 0.12,
            },
            "treatment_b": {
                "exposures": 90000,
                "unique_users": 30000,
                "conversions": 2700,
                "conversion_rate": 0.09,
            },
        }

        result = analyze_experiment(variant_data)

        # Both treatments should have comparative stats
        assert "lift" in result["variants"]["treatment_a"]
        assert "lift" in result["variants"]["treatment_b"]
        assert result["variants"]["treatment_a"]["lift"] > 0
        assert result["variants"]["treatment_b"]["lift"] < 0

    def test_fallback_control_key(self):
        """If no variant named 'control', first variant is used as control."""
        variant_data = {
            "baseline": {
                "exposures": 100000,
                "unique_users": 50000,
                "conversions": 5000,
                "conversion_rate": 0.10,
            },
            "variant_b": {
                "exposures": 100000,
                "unique_users": 50000,
                "conversions": 6000,
                "conversion_rate": 0.12,
            },
        }

        result = analyze_experiment(variant_data)
        # "baseline" should be treated as control (no lift)
        assert "lift" not in result["variants"]["baseline"]
        assert "lift" in result["variants"]["variant_b"]
