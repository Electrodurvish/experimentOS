"""
High-level experiment analysis.

Takes raw variant data from ClickHouse (via query_experiment_results)
and produces a full statistical report.
"""

from apps.stats.engine import (
    is_significant,
    relative_lift,
    required_sample_size,
    srm_test,
    two_proportion_z_test,
    wilson_confidence_interval,
)


def analyze_experiment(variant_data, control_key="control", confidence=0.95):
    """
    Analyze experiment results with statistical tests.

    Args:
        variant_data: dict from query_experiment_results(), keyed by variant_key.
            Each value has: exposures, unique_users, conversions, conversion_rate
        control_key: which variant is the control (default "control")
        confidence: confidence level for intervals (default 0.95)

    Returns dict with:
        - variants: enhanced variant data with CIs, lift, p-values
        - srm: sample ratio mismatch test result
        - sample_size: recommended sample size info
    """
    if not variant_data:
        return {"variants": {}, "srm": None, "sample_size": None}

    # Find control variant
    control = variant_data.get(control_key)
    if not control:
        # If no variant named "control", pick the first is_control or first variant
        control_key = next(iter(variant_data))
        control = variant_data[control_key]

    c_users = control.get("unique_users", 0)
    c_conv = control.get("conversions", 0)

    # Build enhanced variant results
    enhanced_variants = {}

    for key, data in variant_data.items():
        users = data.get("unique_users", 0)
        conv = data.get("conversions", 0)
        rate = conv / users if users > 0 else 0.0

        ci_lower, ci_upper = wilson_confidence_interval(conv, users, confidence)

        variant_result = {
            "exposures": data.get("exposures", 0),
            "unique_users": users,
            "conversions": conv,
            "conversion_rate": round(rate, 6),
            "ci_lower": ci_lower,
            "ci_upper": ci_upper,
        }

        # For non-control variants, add comparative stats
        if key != control_key and c_users > 0:
            z_score, p_value = two_proportion_z_test(c_conv, c_users, conv, users)
            lift_data = relative_lift(c_conv, c_users, conv, users, confidence)

            variant_result.update({
                "lift": lift_data["lift"],
                "lift_ci_lower": lift_data["lift_ci_lower"],
                "lift_ci_upper": lift_data["lift_ci_upper"],
                "absolute_difference": lift_data["absolute_difference"],
                "z_score": z_score,
                "p_value": p_value,
                "is_significant": is_significant(p_value),
            })

        enhanced_variants[key] = variant_result

    # SRM test
    observed_counts = [v.get("unique_users", 0) for v in variant_data.values()]
    num_variants = len(observed_counts)
    expected_props = [1.0 / num_variants] * num_variants if num_variants > 0 else []

    chi2, srm_p = srm_test(observed_counts, expected_props)

    srm_result = {
        "chi_squared": chi2,
        "p_value": srm_p,
        "is_mismatch": srm_p < 0.01,  # SRM uses stricter threshold
        "expected_proportions": {
            key: round(1.0 / num_variants, 4)
            for key in variant_data
        },
        "observed_counts": {
            key: v.get("unique_users", 0)
            for key, v in variant_data.items()
        },
    }

    # Sample size recommendation
    control_rate = c_conv / c_users if c_users > 0 else 0.0
    mde = max(control_rate * 0.05, 0.005) if control_rate > 0 else 0.01  # 5% relative MDE or 0.5% absolute

    sample_size_result = {
        "recommended_per_variant": required_sample_size(control_rate, mde) if control_rate > 0 else 0,
        "baseline_rate": round(control_rate, 6),
        "minimum_detectable_effect": round(mde, 6),
    }

    return {
        "variants": enhanced_variants,
        "srm": srm_result,
        "sample_size": sample_size_result,
    }
