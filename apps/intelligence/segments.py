"""
Segment Analysis Engine.

Breaks down experiment results by user attributes (dimensions like country,
platform, device) and detects:
- Which segments drive the overall effect (contribution analysis)
- Simpson's Paradox (aggregate result differs from segment-level results)
"""

from apps.stats.engine import two_proportion_z_test


def analyze_segments(segment_data, aggregate_lift=0.0):
    """
    Analyze per-segment experiment results.

    Args:
        segment_data: list of segment dicts, each with:
            {
                "dimension": "country",
                "value": "IN",
                "control": {"users": int, "conversions": int},
                "treatment": {"users": int, "conversions": int},
            }
        aggregate_lift: the overall treatment lift (relative)

    Returns:
        {
            "segments": [...],  # enhanced with lift, significance, contribution
            "paradox_detected": bool,
            "paradox_segments": [...],  # segments where direction differs from aggregate
            "top_contributors": [...],  # segments driving most of the effect
        }
    """
    if not segment_data:
        return {
            "segments": [],
            "paradox_detected": False,
            "paradox_segments": [],
            "top_contributors": [],
        }

    analyzed_segments = []
    paradox_segments = []
    total_contribution = 0.0

    for seg in segment_data:
        ctrl = seg.get("control", {})
        treat = seg.get("treatment", {})

        c_users = ctrl.get("users", 0)
        c_conv = ctrl.get("conversions", 0)
        t_users = treat.get("users", 0)
        t_conv = treat.get("conversions", 0)

        c_rate = c_conv / c_users if c_users > 0 else 0.0
        t_rate = t_conv / t_users if t_users > 0 else 0.0

        segment_lift = (t_rate - c_rate) / c_rate if c_rate > 0 else 0.0
        absolute_diff = t_rate - c_rate

        z_score, p_value = two_proportion_z_test(c_conv, c_users, t_conv, t_users)

        # Contribution: how much of the total effect comes from this segment
        # Weight by segment size relative to total
        segment_size = c_users + t_users
        contribution_weight = absolute_diff * segment_size

        result = {
            "dimension": seg.get("dimension", ""),
            "value": seg.get("value", ""),
            "control_users": c_users,
            "control_conversions": c_conv,
            "control_rate": round(c_rate, 6),
            "treatment_users": t_users,
            "treatment_conversions": t_conv,
            "treatment_rate": round(t_rate, 6),
            "lift": round(segment_lift, 6),
            "absolute_difference": round(absolute_diff, 6),
            "z_score": z_score,
            "p_value": p_value,
            "is_significant": p_value < 0.05,
            "contribution_weight": contribution_weight,
        }

        # Check for Simpson's Paradox: segment lift direction differs from aggregate
        has_paradox = False
        if aggregate_lift != 0:
            if (aggregate_lift > 0 and segment_lift < 0) or \
               (aggregate_lift < 0 and segment_lift > 0):
                has_paradox = True
                paradox_segments.append(result)

        result["has_paradox"] = has_paradox
        analyzed_segments.append(result)
        total_contribution += abs(contribution_weight)

    # Normalize contribution percentages
    for seg in analyzed_segments:
        if total_contribution > 0:
            seg["contribution_pct"] = round(
                abs(seg["contribution_weight"]) / total_contribution * 100, 1
            )
        else:
            seg["contribution_pct"] = 0.0

    # Sort by contribution (descending)
    analyzed_segments.sort(key=lambda s: s["contribution_pct"], reverse=True)

    top_contributors = [
        {
            "dimension": s["dimension"],
            "value": s["value"],
            "lift": s["lift"],
            "contribution_pct": s["contribution_pct"],
        }
        for s in analyzed_segments[:5]
        if s["contribution_pct"] > 0
    ]

    return {
        "segments": analyzed_segments,
        "paradox_detected": len(paradox_segments) > 0,
        "paradox_segments": [
            {
                "dimension": s["dimension"],
                "value": s["value"],
                "segment_lift": s["lift"],
                "aggregate_lift": round(aggregate_lift, 6),
            }
            for s in paradox_segments
        ],
        "top_contributors": top_contributors,
    }


def detect_simpsons_paradox(segment_results, aggregate_lift):
    """
    Check if Simpson's Paradox is present.

    Returns True if the aggregate result direction (positive/negative lift)
    is contradicted by the majority of segment-level results.
    """
    if not segment_results or aggregate_lift == 0:
        return False

    contradicting = 0
    total = 0

    for seg in segment_results:
        seg_lift = seg.get("lift", 0)
        if seg_lift == 0:
            continue
        total += 1
        if (aggregate_lift > 0 and seg_lift < 0) or \
           (aggregate_lift < 0 and seg_lift > 0):
            contradicting += 1

    # Paradox if majority of segments contradict aggregate
    if total == 0:
        return False
    return contradicting / total > 0.5
