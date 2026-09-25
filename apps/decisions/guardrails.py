"""
Guardrail evaluation.

Guardrails are evaluated per non-control variant against:
- production telemetry (per-variant averages from ClickHouse), or
- the conversion metric from the statistical analysis.
"""

from apps.decisions.models import GuardrailOperator, GuardrailSource


def evaluate_guardrails(guardrails, telemetry_summary, stats_analysis, control_key="control"):
    """
    Args:
        guardrails: iterable of Guardrail instances (only active ones are evaluated).
        telemetry_summary: output of query_variant_telemetry().
        stats_analysis: output of analyze_experiment().
        control_key: control variant key.

    Returns list of dicts, one per (guardrail, variant):
        {guardrail_id, name, metric_name, source, operator, threshold, action,
         variant_key, observed, control_value, breached, margin, status}
    status is "breached", "healthy" or "no_data".
    """
    results = []
    for guardrail in guardrails:
        if not guardrail.is_active:
            continue

        if guardrail.source == GuardrailSource.CONVERSION:
            per_variant = _conversion_values(stats_analysis)
        else:
            per_variant = _telemetry_values(telemetry_summary, guardrail.metric_name)

        control_value = per_variant.get(control_key)
        treatment_keys = [k for k in per_variant if k != control_key]

        if not treatment_keys:
            results.append(_result(guardrail, None, None, control_value, status="no_data"))
            continue

        for variant_key in treatment_keys:
            observed = _observed_value(guardrail, per_variant[variant_key], control_value)
            if observed is None:
                results.append(_result(guardrail, variant_key, None, control_value, status="no_data"))
                continue
            breached, margin = _check(guardrail, observed)
            results.append(_result(
                guardrail, variant_key, observed, control_value,
                status="breached" if breached else "healthy", margin=margin,
            ))

    return results


def summarize_for_health(guardrail_results):
    """Collapse per-variant results into the shape the health engine expects."""
    by_name = {}
    for r in guardrail_results:
        if r["status"] == "no_data":
            continue
        by_name[r["name"]] = by_name.get(r["name"], False) or r["breached"]
    return [{"name": name, "breached": breached} for name, breached in by_name.items()]


def _conversion_values(stats_analysis):
    variants = (stats_analysis or {}).get("variants", {})
    return {k: v.get("conversion_rate") for k, v in variants.items() if v.get("unique_users")}


def _telemetry_values(telemetry_summary, metric_name):
    values = {}
    for variant_key, metrics in (telemetry_summary or {}).items():
        stats = metrics.get(metric_name)
        if stats and stats.get("count"):
            values[variant_key] = stats.get("avg")
    return values


def _observed_value(guardrail, variant_value, control_value):
    if variant_value is None:
        return None
    if guardrail.operator in (GuardrailOperator.ABSOLUTE_GT, GuardrailOperator.ABSOLUTE_LT):
        return variant_value
    if not control_value:
        return None
    return round((variant_value - control_value) / control_value * 100, 2)


def _check(guardrail, observed):
    """Returns (breached, margin). Margin is how far past the threshold, relative to it."""
    t = guardrail.threshold
    op = guardrail.operator
    if op == GuardrailOperator.RELATIVE_INCREASE_GT:
        breached = observed > t
        overshoot = observed - t
    elif op == GuardrailOperator.RELATIVE_DECREASE_GT:
        breached = -observed > t
        overshoot = -observed - t
    elif op == GuardrailOperator.ABSOLUTE_GT:
        breached = observed > t
        overshoot = observed - t
    else:
        breached = observed < t
        overshoot = t - observed
    margin = round(overshoot / abs(t), 4) if t else (1.0 if breached else 0.0)
    return breached, margin


def _result(guardrail, variant_key, observed, control_value, status, margin=0.0):
    return {
        "guardrail_id": str(guardrail.id),
        "name": guardrail.name,
        "metric_name": guardrail.metric_name,
        "source": guardrail.source,
        "operator": guardrail.operator,
        "threshold": guardrail.threshold,
        "action": guardrail.action,
        "variant_key": variant_key,
        "observed": observed,
        "control_value": control_value,
        "breached": status == "breached",
        "margin": margin,
        "status": status,
    }
