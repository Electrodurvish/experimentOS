"""
Experiment Interaction Detection.

Detects users exposed to multiple concurrent experiments and analyzes
whether combined exposure has different effects than individual exposures.

Creates an experiment dependency graph showing conflicts and interactions.
"""

import logging

from apps.stats.engine import two_proportion_z_test

logger = logging.getLogger(__name__)


def detect_interactions(experiment_pairs):
    """
    Detect interactions between pairs of experiments.

    Args:
        experiment_pairs: list of dicts, each with:
            {
                "experiment_a": str (experiment key),
                "experiment_b": str (experiment key),
                "a_only": {"users": int, "conversions": int},  # users in A only
                "b_only": {"users": int, "conversions": int},  # users in B only
                "both": {"users": int, "conversions": int},     # users in both A and B
                "neither": {"users": int, "conversions": int},  # users in neither
            }

    Returns:
        list of interaction results with significance of combined effect
    """
    if not experiment_pairs:
        return []

    results = []

    for pair in experiment_pairs:
        exp_a = pair.get("experiment_a", "")
        exp_b = pair.get("experiment_b", "")

        a_only = pair.get("a_only", {})
        b_only = pair.get("b_only", {})
        both = pair.get("both", {})
        neither = pair.get("neither", {})

        # Compute conversion rates for each group
        groups = {}
        for name, data in [("a_only", a_only), ("b_only", b_only),
                           ("both", both), ("neither", neither)]:
            users = data.get("users", 0)
            conv = data.get("conversions", 0)
            rate = conv / users if users > 0 else 0.0
            groups[name] = {"users": users, "conversions": conv, "rate": round(rate, 6)}

        # Test: is combined effect (both) different from individual effects?
        # Compare "both" group vs "neither" (baseline)
        combined_z, combined_p = 0.0, 1.0
        if groups["neither"]["users"] > 0 and groups["both"]["users"] > 0:
            combined_z, combined_p = two_proportion_z_test(
                groups["neither"]["conversions"], groups["neither"]["users"],
                groups["both"]["conversions"], groups["both"]["users"],
            )

        # Expected additive effect: (a_only - neither) + (b_only - neither) + neither
        neither_rate = groups["neither"]["rate"]
        a_effect = groups["a_only"]["rate"] - neither_rate
        b_effect = groups["b_only"]["rate"] - neither_rate
        expected_combined_rate = neither_rate + a_effect + b_effect
        actual_combined_rate = groups["both"]["rate"]

        # Interaction = deviation from additive model
        interaction_effect = actual_combined_rate - expected_combined_rate

        # Is the interaction meaningful? (>5% relative deviation)
        is_interaction = (
            abs(interaction_effect) > 0.01 and
            combined_p < 0.05 and
            groups["both"]["users"] >= 100
        )

        interaction_type = "none"
        if is_interaction:
            if interaction_effect > 0:
                interaction_type = "synergistic"
            else:
                interaction_type = "antagonistic"

        results.append({
            "experiment_a": exp_a,
            "experiment_b": exp_b,
            "groups": groups,
            "expected_combined_rate": round(expected_combined_rate, 6),
            "actual_combined_rate": round(actual_combined_rate, 6),
            "interaction_effect": round(interaction_effect, 6),
            "interaction_type": interaction_type,
            "is_interaction": is_interaction,
            "combined_z_score": combined_z,
            "combined_p_value": combined_p,
        })

    return results


def build_interaction_graph(interactions):
    """
    Build an experiment interaction graph from detected interactions.

    Returns:
        {
            "nodes": [{"experiment": str, "interaction_count": int}],
            "edges": [{"from": str, "to": str, "type": str, "effect": float}],
        }
    """
    node_counts = {}
    edges = []

    for interaction in interactions:
        if not interaction.get("is_interaction", False):
            continue

        exp_a = interaction["experiment_a"]
        exp_b = interaction["experiment_b"]

        node_counts[exp_a] = node_counts.get(exp_a, 0) + 1
        node_counts[exp_b] = node_counts.get(exp_b, 0) + 1

        edges.append({
            "from": exp_a,
            "to": exp_b,
            "type": interaction["interaction_type"],
            "effect": interaction["interaction_effect"],
        })

    nodes = [
        {"experiment": exp, "interaction_count": count}
        for exp, count in sorted(node_counts.items(), key=lambda x: x[1], reverse=True)
    ]

    return {"nodes": nodes, "edges": edges}
