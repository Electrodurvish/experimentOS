"""
Gathers every signal the decision engine (and the AI evidence layer) needs
for one experiment, from PostgreSQL, ClickHouse and the intelligence engines.
"""

from apps.decisions.anomaly import detect_timeseries_anomalies, metric_direction
from apps.decisions.engine import DEFAULT_POLICY, harmful_anomalies
from apps.decisions.guardrails import evaluate_guardrails, summarize_for_health
from apps.events.clickhouse import query_experiment_results
from apps.intelligence.health import compute_health_score
from apps.intelligence.segments import analyze_segments
from apps.observability.telemetry import (
    analyze_production_impact,
    query_metric_timeseries,
    query_variant_telemetry,
)
from apps.stats.analyzer import analyze_experiment


def policy_dict(experiment):
    policy = getattr(experiment, "rollout_policy", None)
    if policy is None:
        return dict(DEFAULT_POLICY)
    return {
        "stages": policy.stages,
        "rollback_percentage": policy.rollback_percentage,
        "min_health_score": policy.min_health_score,
    }


def control_and_proportions(experiment):
    """Control variant key and the expected traffic split of the current version."""
    version = experiment.current_version
    if not version:
        return "control", None
    variants = list(version.variants.all())
    control = next((v.key for v in variants if v.is_control), "control")
    total = sum(v.traffic_percentage for v in variants)
    proportions = {v.key: v.traffic_percentage / total for v in variants} if total else None
    return control, proportions


def gather_inputs(experiment, segments=None, interactions=None):
    """
    Args:
        experiment: Experiment instance.
        segments: optional raw segment data (same shape as the segments endpoint).
        interactions: optional detect_interactions() output involving this experiment.

    Returns the dict consumed by apps.decisions.engine.decide().
    """
    control_key, proportions = control_and_proportions(experiment)

    raw_variants = query_experiment_results(str(experiment.id))
    stats = analyze_experiment(raw_variants, control_key=control_key, expected_proportions=proportions)

    telemetry = query_variant_telemetry(str(experiment.id))
    production_impact = analyze_production_impact(telemetry, control_key=control_key)

    guardrail_results = evaluate_guardrails(
        experiment.guardrails.all(), telemetry, stats, control_key=control_key,
    )

    segment_analysis = None
    if segments:
        aggregate_lift = next(
            (v["lift"] for k, v in stats["variants"].items() if k != control_key and "lift" in v),
            0.0,
        )
        segment_analysis = analyze_segments(segments, aggregate_lift)

    health = compute_health_score(
        raw_variants,
        expected_proportions=proportions,
        guardrail_results=summarize_for_health(guardrail_results),
        segment_data=segment_analysis["segments"] if segment_analysis else None,
    )

    anomalies = detect_experiment_anomalies(experiment, telemetry, control_key)

    return {
        "status": experiment.status,
        "rollout_percentage": experiment.rollout_percentage,
        "policy": policy_dict(experiment),
        "control_key": control_key,
        "stats": stats,
        "health": health,
        "guardrails": guardrail_results,
        "telemetry": telemetry,
        "production_impact": production_impact,
        "anomalies": anomalies,
        "segments": segment_analysis,
        "interactions": interactions or [],
    }


def detect_experiment_anomalies(experiment, telemetry, control_key):
    """Run time-series anomaly detection for every telemetry metric reported for the experiment."""
    metric_names = sorted({m for metrics in (telemetry or {}).values() for m in metrics})
    by_metric = {}
    for metric_name in metric_names:
        series = query_metric_timeseries(str(experiment.id), metric_name)
        direction = metric_direction(metric_name)
        by_metric[metric_name] = {
            variant_key: detect_timeseries_anomalies(points, direction=direction)
            for variant_key, points in series.items()
        }
    return harmful_anomalies(by_metric, control_key=control_key)


def decision_snapshot(inputs):
    """The subset of inputs worth persisting alongside a decision."""
    return {
        "rollout_percentage": inputs["rollout_percentage"],
        "health_score": (inputs.get("health") or {}).get("overall_score"),
        "variants": (inputs.get("stats") or {}).get("variants"),
        "srm": (inputs.get("stats") or {}).get("srm"),
        "guardrails": inputs.get("guardrails"),
        "production_impact": inputs.get("production_impact"),
        "anomaly_count": len(inputs.get("anomalies") or []),
    }
