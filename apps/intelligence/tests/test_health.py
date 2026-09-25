from apps.intelligence.health import compute_health_score

HEALTHY_DATA = {
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


class TestHealthScore:
    def test_healthy_experiment_high_score(self):
        result = compute_health_score(HEALTHY_DATA)
        assert result["overall_score"] >= 70
        assert "dimensions" in result
        assert len(result["dimensions"]) == 6

    def test_all_dimensions_present(self):
        result = compute_health_score(HEALTHY_DATA)
        expected = [
            "sample_ratio", "data_quality", "statistical_power",
            "exposure_quality", "segment_stability", "guardrail_health",
        ]
        for dim in expected:
            assert dim in result["dimensions"]
            assert "score" in result["dimensions"][dim]
            assert "detail" in result["dimensions"][dim]

    def test_empty_data_low_score(self):
        result = compute_health_score({})
        assert result["overall_score"] <= 50

    def test_imbalanced_sample_ratio(self):
        imbalanced = {
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
        result = compute_health_score(imbalanced)
        assert result["dimensions"]["sample_ratio"]["score"] < 50

    def test_low_sample_size(self):
        low_sample = {
            "control": {
                "exposures": 20,
                "unique_users": 10,
                "conversions": 1,
                "conversion_rate": 0.10,
            },
            "treatment": {
                "exposures": 20,
                "unique_users": 10,
                "conversions": 2,
                "conversion_rate": 0.20,
            },
        }
        result = compute_health_score(low_sample)
        assert result["dimensions"]["statistical_power"]["score"] < 50

    def test_high_duplicate_exposures(self):
        high_dupes = {
            "control": {
                "exposures": 500000,
                "unique_users": 50000,
                "conversions": 5000,
                "conversion_rate": 0.10,
            },
            "treatment": {
                "exposures": 500000,
                "unique_users": 50000,
                "conversions": 6000,
                "conversion_rate": 0.12,
            },
        }
        result = compute_health_score(high_dupes)
        assert result["dimensions"]["exposure_quality"]["score"] < 50

    def test_guardrails_breached(self):
        guardrails = [
            {"name": "error_rate", "breached": True},
            {"name": "latency", "breached": False},
        ]
        result = compute_health_score(HEALTHY_DATA, guardrail_results=guardrails)
        assert result["dimensions"]["guardrail_health"]["score"] < 50

    def test_no_guardrails_full_score(self):
        result = compute_health_score(HEALTHY_DATA, guardrail_results=None)
        assert result["dimensions"]["guardrail_health"]["score"] == 100

    def test_segment_stability_with_paradox(self):
        segments = [
            {"has_paradox": True},
            {"has_paradox": False},
        ]
        result = compute_health_score(HEALTHY_DATA, segment_data=segments)
        assert result["dimensions"]["segment_stability"]["score"] < 100

    def test_score_is_bounded(self):
        result = compute_health_score(HEALTHY_DATA)
        assert 0 <= result["overall_score"] <= 100
        for dim_data in result["dimensions"].values():
            assert 0 <= dim_data["score"] <= 100
