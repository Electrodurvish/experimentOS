from apps.intelligence.segments import analyze_segments, detect_simpsons_paradox

SEGMENT_DATA = [
    {
        "dimension": "platform",
        "value": "android",
        "control": {"users": 20000, "conversions": 2000},
        "treatment": {"users": 20000, "conversions": 2800},
    },
    {
        "dimension": "platform",
        "value": "ios",
        "control": {"users": 15000, "conversions": 1500},
        "treatment": {"users": 15000, "conversions": 1530},
    },
    {
        "dimension": "platform",
        "value": "web",
        "control": {"users": 15000, "conversions": 1500},
        "treatment": {"users": 15000, "conversions": 1605},
    },
]


class TestAnalyzeSegments:
    def test_basic_analysis(self):
        result = analyze_segments(SEGMENT_DATA, aggregate_lift=0.20)

        assert len(result["segments"]) == 3
        assert "paradox_detected" in result
        assert "top_contributors" in result

    def test_segment_has_statistics(self):
        result = analyze_segments(SEGMENT_DATA, aggregate_lift=0.20)

        for seg in result["segments"]:
            assert "lift" in seg
            assert "p_value" in seg
            assert "is_significant" in seg
            assert "contribution_pct" in seg
            assert "has_paradox" in seg

    def test_contribution_sums_to_100(self):
        result = analyze_segments(SEGMENT_DATA, aggregate_lift=0.20)

        total = sum(s["contribution_pct"] for s in result["segments"])
        assert abs(total - 100.0) < 1.0  # Allow rounding

    def test_top_contributors_sorted(self):
        result = analyze_segments(SEGMENT_DATA, aggregate_lift=0.20)

        contributors = result["top_contributors"]
        if len(contributors) >= 2:
            for i in range(len(contributors) - 1):
                assert contributors[i]["contribution_pct"] >= contributors[i + 1]["contribution_pct"]

    def test_android_drives_most_lift(self):
        result = analyze_segments(SEGMENT_DATA, aggregate_lift=0.20)

        # Android has the highest lift (40% vs 2% and 7%), should be top contributor
        top = result["top_contributors"][0]
        assert top["value"] == "android"

    def test_no_paradox_when_all_positive(self):
        result = analyze_segments(SEGMENT_DATA, aggregate_lift=0.20)
        assert result["paradox_detected"] is False

    def test_paradox_detected(self):
        paradox_data = [
            {
                "dimension": "platform",
                "value": "android",
                "control": {"users": 10000, "conversions": 1200},
                "treatment": {"users": 10000, "conversions": 1100},  # negative
            },
            {
                "dimension": "platform",
                "value": "ios",
                "control": {"users": 10000, "conversions": 1000},
                "treatment": {"users": 10000, "conversions": 900},  # negative
            },
        ]

        result = analyze_segments(paradox_data, aggregate_lift=0.10)  # aggregate positive
        assert result["paradox_detected"] is True
        assert len(result["paradox_segments"]) == 2

    def test_empty_segments(self):
        result = analyze_segments([], aggregate_lift=0.10)
        assert result["segments"] == []
        assert result["paradox_detected"] is False

    def test_zero_users(self):
        data = [
            {
                "dimension": "country",
                "value": "US",
                "control": {"users": 0, "conversions": 0},
                "treatment": {"users": 0, "conversions": 0},
            },
        ]
        result = analyze_segments(data, aggregate_lift=0.10)
        assert len(result["segments"]) == 1


class TestDetectSimpsonsParadox:
    def test_no_paradox(self):
        segments = [{"lift": 0.10}, {"lift": 0.05}, {"lift": 0.15}]
        assert detect_simpsons_paradox(segments, 0.10) is False

    def test_paradox_majority_contradict(self):
        segments = [{"lift": -0.05}, {"lift": -0.03}, {"lift": 0.20}]
        assert detect_simpsons_paradox(segments, 0.10) is True

    def test_empty_segments(self):
        assert detect_simpsons_paradox([], 0.10) is False

    def test_zero_aggregate_lift(self):
        segments = [{"lift": -0.05}, {"lift": 0.05}]
        assert detect_simpsons_paradox(segments, 0.0) is False
