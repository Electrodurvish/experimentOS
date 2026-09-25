"""
Metrics engine: analyze every configured metric (primary, secondary, guardrail).

CONVERSION metrics compare the share of users with the event (two-proportion
z-test, Wilson CIs). MEAN_VALUE metrics compare the mean event value per exposed
user, e.g. revenue per user (Welch test on per-user totals).
"""

from apps.events.clickhouse import query_metric_values
from apps.stats.engine import (
    is_significant,
    mean_difference_test,
    relative_lift,
    two_proportion_z_test,
    wilson_confidence_interval,
)
from apps.stats.models import MetricAggregation


def analyze_metric(metric, per_variant, control_key="control"):
    """
    Args:
        metric: ExperimentMetric
        per_variant: output of query_metric_values()
    Returns:
        {"name", "event_name", "metric_type", "aggregation", "variants": {key: {...}}}
    """
    control = per_variant.get(control_key)
    variants = {}
    for key, v in per_variant.items():
        users = v["users"]
        if metric.aggregation == MetricAggregation.MEAN_VALUE:
            mean = v["total_value"] / users if users else 0.0
            variance = (v["total_value_sq"] / users - mean * mean) * users / (users - 1) if users > 1 else 0.0
            row = {"users": users, "value": round(mean, 6), "variance": round(max(variance, 0.0), 6)}
        else:
            rate = v["converters"] / users if users else 0.0
            lower, upper = wilson_confidence_interval(v["converters"], users)
            row = {"users": users, "converters": v["converters"], "value": round(rate, 6),
                   "ci_lower": lower, "ci_upper": upper}
        variants[key] = row

    if control and control["users"]:
        c = variants[control_key]
        for key, row in variants.items():
            if key == control_key or not row["users"]:
                continue
            if metric.aggregation == MetricAggregation.MEAN_VALUE:
                test = mean_difference_test(c["value"], c["variance"], c["users"],
                                            row["value"], row["variance"], row["users"])
                row.update({
                    "lift": test["lift"], "difference": test["difference"],
                    "diff_ci_lower": test["ci_lower"], "diff_ci_upper": test["ci_upper"],
                    "p_value": test["p_value"],
                })
            else:
                _, p_value = two_proportion_z_test(control["converters"], control["users"],
                                                   per_variant[key]["converters"], row["users"])
                lift = relative_lift(control["converters"], control["users"],
                                     per_variant[key]["converters"], row["users"])
                row.update({"lift": lift["lift"], "difference": lift["absolute_difference"], "p_value": p_value})
            row["is_significant"] = is_significant(row["p_value"])

    return {
        "id": str(metric.id),
        "name": metric.name,
        "event_name": metric.event_name,
        "metric_type": metric.metric_type,
        "aggregation": metric.aggregation,
        "variants": variants,
    }


def analyze_metrics(experiment, control_key="control", metric_types=None):
    metrics = experiment.metrics.all()
    if metric_types:
        metrics = metrics.filter(metric_type__in=metric_types)
    return [
        analyze_metric(metric, query_metric_values(str(experiment.id), metric.event_name), control_key)
        for metric in metrics.order_by("metric_type", "name")
    ]
