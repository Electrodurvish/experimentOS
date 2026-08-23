"""
Experiment Health Score Engine.

Calculates a composite health score (0-100) across multiple dimensions:
- Sample Ratio: Are variants receiving expected traffic proportions?
- Data Quality: Is data complete and consistent?
- Statistical Power: Do we have enough samples to detect meaningful effects?
- Exposure Quality: Are exposure events firing correctly?
- Segment Stability: Are segment-level results consistent with aggregate?
- Guardrail Health: Are guardrail metrics within acceptable bounds?

Each dimension is scored 0-100 and combined with weighted average.
"""

import math

from apps.stats.engine import required_sample_size, srm_test


# Dimension weights (must sum to 1.0)
DIMENSION_WEIGHTS = {
    "sample_ratio": 0.20,
    "data_quality": 0.15,
    "statistical_power": 0.20,
    "exposure_quality": 0.15,
    "segment_stability": 0.15,
    "guardrail_health": 0.15,
}


def compute_health_score(
    variant_data,
    expected_proportions=None,
    guardrail_results=None,
    segment_data=None,
):
    """
    Compute the overall experiment health score.

    Args:
        variant_data: dict of variant_key -> {unique_users, exposures, conversions, conversion_rate}
        expected_proportions: dict of variant_key -> expected proportion (default: equal split)
        guardrail_results: list of dicts with {name, breached: bool}
        segment_data: list of segment analysis results for stability check

    Returns:
        {
            "overall_score": int (0-100),
            "dimensions": {
                "sample_ratio": {"score": int, "detail": str},
                "data_quality": {"score": int, "detail": str},
                ...
            }
        }
    """
    dimensions = {}

    dimensions["sample_ratio"] = _score_sample_ratio(variant_data, expected_proportions)
    dimensions["data_quality"] = _score_data_quality(variant_data)
    dimensions["statistical_power"] = _score_statistical_power(variant_data)
    dimensions["exposure_quality"] = _score_exposure_quality(variant_data)
    dimensions["segment_stability"] = _score_segment_stability(segment_data)
    dimensions["guardrail_health"] = _score_guardrail_health(guardrail_results)

    overall = sum(
        dimensions[dim]["score"] * DIMENSION_WEIGHTS[dim]
        for dim in DIMENSION_WEIGHTS
    )

    return {
        "overall_score": round(overall),
        "dimensions": dimensions,
    }


def _score_sample_ratio(variant_data, expected_proportions=None):
    """Score based on SRM test. Perfect ratio = 100, severe mismatch = 0."""
    if not variant_data or len(variant_data) < 2:
        return {"score": 100, "detail": "Not enough variants for SRM check."}

    observed = [v.get("unique_users", 0) for v in variant_data.values()]
    total = sum(observed)

    if total == 0:
        return {"score": 0, "detail": "No users observed."}

    if expected_proportions:
        props = [expected_proportions.get(k, 1.0 / len(variant_data)) for k in variant_data]
    else:
        props = [1.0 / len(variant_data)] * len(variant_data)

    chi2, p_value = srm_test(observed, props)

    if p_value >= 0.05:
        score = 100
        detail = f"Sample ratio is balanced (p={p_value})."
    elif p_value >= 0.01:
        score = 70
        detail = f"Minor sample ratio imbalance (p={p_value})."
    elif p_value >= 0.001:
        score = 40
        detail = f"Sample ratio mismatch detected (p={p_value})."
    else:
        score = 10
        detail = f"Severe sample ratio mismatch (p={p_value})."

    return {"score": score, "detail": detail}


def _score_data_quality(variant_data):
    """Score based on data completeness. Checks for zero/missing values."""
    if not variant_data:
        return {"score": 0, "detail": "No variant data available."}

    issues = 0
    total_checks = 0

    for key, data in variant_data.items():
        total_checks += 3
        if data.get("unique_users", 0) == 0:
            issues += 1
        if data.get("exposures", 0) == 0:
            issues += 1
        # Check if exposures >= unique_users (sanity)
        if data.get("exposures", 0) < data.get("unique_users", 0):
            issues += 1

    if total_checks == 0:
        return {"score": 100, "detail": "No data to check."}

    score = max(0, round(100 * (1 - issues / total_checks)))

    if score == 100:
        detail = "All data quality checks passed."
    elif score >= 70:
        detail = f"Minor data quality issues ({issues} checks failed)."
    else:
        detail = f"Significant data quality issues ({issues} checks failed)."

    return {"score": score, "detail": detail}


def _score_statistical_power(variant_data):
    """Score based on whether we have enough samples for meaningful results."""
    if not variant_data:
        return {"score": 0, "detail": "No data available."}

    # Find control rate
    control_data = variant_data.get("control")
    if not control_data:
        control_data = next(iter(variant_data.values()))

    users = control_data.get("unique_users", 0)
    conv = control_data.get("conversions", 0)

    if users == 0:
        return {"score": 0, "detail": "No users in control group."}

    rate = conv / users
    if rate <= 0 or rate >= 1:
        return {"score": 50, "detail": "Cannot estimate power with extreme conversion rate."}

    # Calculate required sample for 5% relative MDE
    mde = max(rate * 0.05, 0.005)
    needed = required_sample_size(rate, mde)

    if needed == 0:
        return {"score": 50, "detail": "Cannot estimate required sample size."}

    # Score based on % of required sample achieved
    ratio = users / needed
    if ratio >= 1.0:
        score = 100
        detail = f"Sufficient sample size ({users:,} / {needed:,} needed)."
    elif ratio >= 0.75:
        score = 80
        detail = f"Nearly sufficient sample ({users:,} / {needed:,} needed, {ratio:.0%})."
    elif ratio >= 0.50:
        score = 60
        detail = f"Moderate sample size ({users:,} / {needed:,} needed, {ratio:.0%})."
    elif ratio >= 0.25:
        score = 35
        detail = f"Low sample size ({users:,} / {needed:,} needed, {ratio:.0%})."
    else:
        score = 15
        detail = f"Very low sample size ({users:,} / {needed:,} needed, {ratio:.0%})."

    return {"score": score, "detail": detail}


def _score_exposure_quality(variant_data):
    """
    Score based on exposure-to-user ratio consistency.
    Ideally exposure count should be close to or slightly above unique users.
    Very high ratios may indicate duplicate exposure logging.
    """
    if not variant_data:
        return {"score": 0, "detail": "No data available."}

    ratios = []
    for data in variant_data.values():
        users = data.get("unique_users", 0)
        exposures = data.get("exposures", 0)
        if users > 0:
            ratios.append(exposures / users)

    if not ratios:
        return {"score": 0, "detail": "No users observed."}

    avg_ratio = sum(ratios) / len(ratios)

    if avg_ratio <= 1.5:
        score = 100
        detail = f"Clean exposure logging (avg {avg_ratio:.1f} exposures/user)."
    elif avg_ratio <= 3.0:
        score = 80
        detail = f"Moderate duplicate exposures (avg {avg_ratio:.1f} exposures/user)."
    elif avg_ratio <= 5.0:
        score = 50
        detail = f"High duplicate exposure rate (avg {avg_ratio:.1f} exposures/user)."
    else:
        score = 20
        detail = f"Excessive duplicate exposures (avg {avg_ratio:.1f} exposures/user)."

    return {"score": score, "detail": detail}


def _score_segment_stability(segment_data):
    """
    Score based on consistency between segment-level and aggregate results.
    Checks for Simpson's Paradox indicators.
    """
    if not segment_data:
        return {"score": 100, "detail": "No segment data available for stability check."}

    paradox_count = 0
    total_segments = 0

    for segment in segment_data:
        if isinstance(segment, dict) and "has_paradox" in segment:
            total_segments += 1
            if segment["has_paradox"]:
                paradox_count += 1

    if total_segments == 0:
        return {"score": 100, "detail": "No segment comparisons available."}

    if paradox_count == 0:
        score = 100
        detail = "Segment results are consistent with aggregate."
    elif paradox_count == 1:
        score = 60
        detail = f"Potential Simpson's Paradox in {paradox_count} segment."
    else:
        score = 30
        detail = f"Simpson's Paradox detected in {paradox_count} segments."

    return {"score": score, "detail": detail}


def _score_guardrail_health(guardrail_results):
    """Score based on guardrail metric status."""
    if not guardrail_results:
        return {"score": 100, "detail": "No guardrail metrics configured."}

    breached = sum(1 for g in guardrail_results if g.get("breached", False))
    total = len(guardrail_results)

    if breached == 0:
        score = 100
        detail = f"All {total} guardrail metrics are healthy."
    elif breached == 1:
        score = 40
        detail = f"{breached}/{total} guardrail breached."
    else:
        score = 10
        detail = f"{breached}/{total} guardrails breached."

    return {"score": score, "detail": detail}
