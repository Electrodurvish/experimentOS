from apps.intelligence.interactions import build_interaction_graph, detect_interactions


class TestDetectInteractions:
    def test_no_interaction(self):
        pairs = [
            {
                "experiment_a": "checkout_v3",
                "experiment_b": "pricing_v2",
                "a_only": {"users": 10000, "conversions": 1000},
                "b_only": {"users": 10000, "conversions": 1100},
                "both": {"users": 10000, "conversions": 1200},
                "neither": {"users": 10000, "conversions": 900},
            },
        ]

        results = detect_interactions(pairs)
        assert len(results) == 1
        # Expected combined: 0.09 + (0.10 - 0.09) + (0.11 - 0.09) = 0.12
        # Actual: 0.12, so no interaction
        assert results[0]["interaction_type"] == "none"

    def test_synergistic_interaction(self):
        pairs = [
            {
                "experiment_a": "checkout_v3",
                "experiment_b": "pricing_v2",
                "a_only": {"users": 10000, "conversions": 1000},
                "b_only": {"users": 10000, "conversions": 1100},
                "both": {"users": 10000, "conversions": 1800},  # much higher
                "neither": {"users": 10000, "conversions": 900},
            },
        ]

        results = detect_interactions(pairs)
        assert len(results) == 1
        assert results[0]["interaction_effect"] > 0
        # Actual is much higher than expected additive

    def test_antagonistic_interaction(self):
        pairs = [
            {
                "experiment_a": "checkout_v3",
                "experiment_b": "pricing_v2",
                "a_only": {"users": 10000, "conversions": 1200},
                "b_only": {"users": 10000, "conversions": 1300},
                "both": {"users": 10000, "conversions": 800},  # much lower
                "neither": {"users": 10000, "conversions": 1000},
            },
        ]

        results = detect_interactions(pairs)
        assert len(results) == 1
        assert results[0]["interaction_effect"] < 0

    def test_empty_pairs(self):
        results = detect_interactions([])
        assert results == []

    def test_result_structure(self):
        pairs = [
            {
                "experiment_a": "exp_a",
                "experiment_b": "exp_b",
                "a_only": {"users": 5000, "conversions": 500},
                "b_only": {"users": 5000, "conversions": 550},
                "both": {"users": 5000, "conversions": 600},
                "neither": {"users": 5000, "conversions": 450},
            },
        ]

        results = detect_interactions(pairs)
        result = results[0]

        assert "experiment_a" in result
        assert "experiment_b" in result
        assert "groups" in result
        assert "expected_combined_rate" in result
        assert "actual_combined_rate" in result
        assert "interaction_effect" in result
        assert "interaction_type" in result
        assert "is_interaction" in result

    def test_zero_users_handled(self):
        pairs = [
            {
                "experiment_a": "a",
                "experiment_b": "b",
                "a_only": {"users": 0, "conversions": 0},
                "b_only": {"users": 0, "conversions": 0},
                "both": {"users": 0, "conversions": 0},
                "neither": {"users": 0, "conversions": 0},
            },
        ]
        results = detect_interactions(pairs)
        assert len(results) == 1
        assert results[0]["is_interaction"] is False


class TestBuildInteractionGraph:
    def test_no_interactions(self):
        interactions = [
            {"experiment_a": "a", "experiment_b": "b", "is_interaction": False,
             "interaction_type": "none", "interaction_effect": 0.0}
        ]
        graph = build_interaction_graph(interactions)
        assert graph["nodes"] == []
        assert graph["edges"] == []

    def test_with_interactions(self):
        interactions = [
            {"experiment_a": "checkout", "experiment_b": "pricing",
             "is_interaction": True, "interaction_type": "synergistic",
             "interaction_effect": 0.05},
            {"experiment_a": "checkout", "experiment_b": "payment",
             "is_interaction": True, "interaction_type": "antagonistic",
             "interaction_effect": -0.03},
        ]
        graph = build_interaction_graph(interactions)

        assert len(graph["edges"]) == 2
        assert len(graph["nodes"]) == 3

        # Checkout should have highest interaction count
        checkout_node = next(n for n in graph["nodes"] if n["experiment"] == "checkout")
        assert checkout_node["interaction_count"] == 2

    def test_empty_interactions(self):
        graph = build_interaction_graph([])
        assert graph["nodes"] == []
        assert graph["edges"] == []
