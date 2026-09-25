"""
Decision Engine + Explainability.

Combines experiment results, health score, guardrails, production telemetry,
anomalies, segment analysis and experiment interactions into one of:

    CONTINUE, PAUSE, ROLLBACK, INCREASE_ROLLOUT, DECREASE_ROLLOUT, COMPLETE

Every recommendation carries numbered evidence and the checks it passed or
failed, so a human (or the AI layer) can see exactly why it was made:

    Recommendation: ROLLBACK
    Evidence:
      E1. Guardrail "Error rate" breached for treatment: +312.0% vs control (threshold 20.0%).
      E2. Primary metric lift for treatment is +2.1% (p=0.2100, not significant).
    Confidence: HIGH

decide() is a pure function over plain dicts; gathering the inputs lives in
apps.decisions.context, acting on the result lives in apps.decisions.rollout.
"""

from dataclasses import asdict, dataclass, field

from apps.decisions.anomaly import metric_direction
from apps.decisions.models import DEFAULT_ROLLOUT_STAGES, GuardrailAction, Recommendation

DEFAULT_POLICY = {
    "stages": DEFAULT_ROLLOUT_STAGES,
    "rollback_percentage": 1000,
    "min_health_score": 70,
}

CRITICAL_HEALTH_SCORE = 40


@dataclass
class DecisionResult:
    recommendation: str
    confidence: float
    confidence_label: str
    summary: str
    evidence: list = field(default_factory=list)
    checks: list = field(default_factory=list)
    target_percentage: int | None = None

    def to_dict(self):
        return asdict(self)


class _Evidence:
    def __init__(self):
        self.items = []

    def add(self, kind, statement, **data):
        self.items.append({
            "id": f"E{len(self.items) + 1}",
            "kind": kind,
            "statement": statement,
            "data": data,
        })


def confidence_label(confidence):
    if confidence >= 0.8:
        return "HIGH"
    if confidence >= 0.6:
        return "MEDIUM"
    return "LOW"


def next_stage(stages, current):
    """The first stage strictly above the current rollout, or None at the top."""
    for stage in sorted(stages):
        if stage > current:
            return stage
    return None


def previous_stage(stages, current):
    """The last stage strictly below the current rollout, or None at the bottom."""
    below = [s for s in sorted(stages) if s < current]
    return below[-1] if below else None


def decide(inputs):
    """
    Args:
        inputs: dict with keys
            status, rollout_percentage, policy, control_key,
            stats (analyze_experiment), health (compute_health_score),
            guardrails (evaluate_guardrails), production_impact (analyze_production_impact),
            anomalies (list of time-series anomalies with variant_key/metric_name),
            segments (analyze_segments, optional), interactions (detect_interactions, optional)

    Returns DecisionResult.
    """
    policy = {**DEFAULT_POLICY, **(inputs.get("policy") or {})}
    rollout = inputs.get("rollout_percentage", 10000)
    control_key = inputs.get("control_key", "control")
    status = inputs.get("status", "RUNNING")

    evidence = _Evidence()
    checks = _build_checks(inputs, policy, control_key, evidence)
    check_map = {c["name"]: c for c in checks}

    def result(recommendation, confidence, summary, target=None):
        confidence = round(max(0.0, min(0.99, confidence)), 2)
        return DecisionResult(
            recommendation=recommendation,
            confidence=confidence,
            confidence_label=confidence_label(confidence),
            summary=summary,
            evidence=evidence.items,
            checks=checks,
            target_percentage=target,
        )

    if status != "RUNNING":
        return result(
            Recommendation.CONTINUE, 0.99,
            f"Experiment is {status}; automated decisions only apply to running experiments.",
        )

    stages = policy["stages"]
    rollback_to = policy["rollback_percentage"]

    # 1. Guardrail breaches — the hard safety net.
    breaches = [g for g in inputs.get("guardrails") or [] if g.get("breached")]
    if breaches:
        worst = max(breaches, key=lambda g: g.get("margin", 0))
        confidence = 0.75 + 0.2 * min(1.0, max(0.0, worst.get("margin", 0)))
        names = ", ".join(sorted({g["name"] for g in breaches}))
        if any(g["action"] == GuardrailAction.ROLLBACK for g in breaches):
            if rollout > rollback_to:
                return result(
                    Recommendation.ROLLBACK, confidence,
                    f"Roll back from {_pct(rollout)} to {_pct(rollback_to)}: guardrail breached ({names}).",
                    target=rollback_to,
                )
            return result(
                Recommendation.PAUSE, confidence,
                f"Pause: guardrail breached ({names}) and rollout is already at the rollback floor.",
            )
        return result(Recommendation.PAUSE, confidence, f"Pause: guardrail breached ({names}).")

    # 2. Critical production anomalies in the harmful direction.
    critical = [a for a in inputs.get("anomalies") or [] if a.get("severity") == "critical"]
    if critical:
        metrics = ", ".join(sorted({a["metric_name"] for a in critical}))
        target = previous_stage(stages, rollout)
        if target is None or target >= rollout:
            return result(Recommendation.PAUSE, 0.75, f"Pause: critical anomaly detected in {metrics}.")
        return result(
            Recommendation.DECREASE_ROLLOUT, 0.75,
            f"Decrease rollout to {_pct(target)}: critical anomaly detected in {metrics}.",
            target=target,
        )

    # 3. Sample ratio mismatch — results cannot be trusted.
    if not check_map["srm_not_detected"]["passed"]:
        return result(
            Recommendation.PAUSE, 0.9,
            "Pause: sample ratio mismatch means assignment or logging is broken; results are untrustworthy.",
        )

    # 4. Statistically significant harm to the primary metric.
    harmed = _significant_regressions(inputs.get("stats"), control_key)
    if harmed:
        key, data = min(harmed, key=lambda kv: kv[1]["p_value"])
        confidence = 1.0 - data["p_value"]
        if rollout > rollback_to:
            return result(
                Recommendation.ROLLBACK, confidence,
                f"Roll back to {_pct(rollback_to)}: {key} significantly lowers the primary metric "
                f"({data['lift'] * 100:+.1f}%).",
                target=rollback_to,
            )
        return result(
            Recommendation.PAUSE, confidence,
            f"Pause: {key} significantly lowers the primary metric ({data['lift'] * 100:+.1f}%).",
        )

    # 5. Production regressions without an explicit guardrail.
    if not check_map["production_healthy"]["passed"]:
        target = previous_stage(stages, rollout)
        if target is not None:
            return result(
                Recommendation.DECREASE_ROLLOUT, 0.7,
                f"Decrease rollout to {_pct(target)}: production telemetry regressed critically.",
                target=target,
            )
        return result(Recommendation.CONTINUE, 0.6, "Hold: production telemetry regressed; do not expand rollout.")

    # 6. Untrustworthy experiment — hold, or pause if very unhealthy.
    health_score = (inputs.get("health") or {}).get("overall_score")
    if health_score is not None and health_score < CRITICAL_HEALTH_SCORE:
        return result(
            Recommendation.PAUSE, 0.7,
            f"Pause: experiment health score {health_score}/100 is critically low.",
        )
    if not check_map["health_score_ok"]["passed"]:
        return result(
            Recommendation.CONTINUE, 0.65,
            f"Hold rollout: health score {health_score}/100 is below the policy minimum "
            f"of {policy['min_health_score']}.",
        )

    # 7. Positive path: expand, or complete at full rollout.
    passed = sum(1 for c in checks if c["passed"])
    passed_ratio = passed / len(checks) if checks else 0.0
    winner = _best_significant_winner(inputs.get("stats"), control_key)
    ready = (
        winner is not None
        and check_map["sufficient_sample_size"]["passed"]
        and check_map["no_segment_regressions"]["passed"]
        and check_map["no_interactions"]["passed"]
    )
    if ready:
        key, data = winner
        confidence = passed_ratio * (1.0 - data["p_value"])
        target = next_stage(stages, rollout)
        if target is None:
            return result(
                Recommendation.COMPLETE, confidence,
                f"Complete: {key} wins with {data['lift'] * 100:+.1f}% lift at full rollout; ship it.",
            )
        return result(
            Recommendation.INCREASE_ROLLOUT, confidence,
            f"Increase rollout from {_pct(rollout)} to {_pct(target)}: {key} improves the primary "
            f"metric by {data['lift'] * 100:+.1f}% and all safety checks pass.",
            target=target,
        )

    # 8. Nothing conclusive yet.
    failing = [c["label"] for c in checks if not c["passed"]]
    reason = f" Waiting on: {', '.join(failing)}." if failing else ""
    return result(
        Recommendation.CONTINUE, 0.5 + 0.3 * passed_ratio,
        f"Continue at {_pct(rollout)}: not enough evidence to change the rollout.{reason}",
    )


# ── Checks ──


def _build_checks(inputs, policy, control_key, evidence):
    stats = inputs.get("stats") or {}
    variants = stats.get("variants") or {}
    checks = []

    def check(name, label, passed, detail):
        checks.append({"name": name, "label": label, "passed": bool(passed), "detail": detail})

    # Primary metric
    winner = _best_significant_winner(stats, control_key)
    treatments = {k: v for k, v in variants.items() if k != control_key and v.get("lift") is not None}
    if winner:
        key, data = winner
        detail = f"{key} lift {data['lift'] * 100:+.1f}% (p={data['p_value']:.4f})."
        evidence.add("primary_metric", f"Primary metric improved: {detail}",
                     variant=key, lift=data["lift"], p_value=data["p_value"])
    elif treatments:
        key, data = max(treatments.items(), key=lambda kv: kv[1]["lift"])
        detail = f"Best variant {key} lift {data['lift'] * 100:+.1f}% (p={data['p_value']:.4f}, not significant)."
        evidence.add("primary_metric", f"Primary metric not significantly improved: {detail}",
                     variant=key, lift=data["lift"], p_value=data["p_value"])
    else:
        detail = "No variant data yet."
    check("primary_metric_improved", "Primary metric improved", winner is not None, detail)

    # Secondary / guardrail metrics (evidence only; enforcement is via Guardrail rules)
    for m in inputs.get("metrics") or []:
        if m.get("metric_type") == "PRIMARY":
            continue
        for key, v in m.get("variants", {}).items():
            if key != control_key and v.get("is_significant") and v.get("lift") is not None:
                evidence.add(
                    "metric",
                    f"{m['metric_type'].title()} metric \"{m['name']}\" for {key} changed "
                    f"{v['lift'] * 100:+.1f}% (p={v['p_value']:.4f}).",
                    metric=m["name"], variant=key, lift=v["lift"],
                )

    # Guardrails
    guardrails = inputs.get("guardrails") or []
    breaches = [g for g in guardrails if g.get("breached")]
    for g in breaches:
        evidence.add(
            "guardrail",
            f"Guardrail \"{g['name']}\" breached for {g['variant_key']}: {_fmt_observed(g)} "
            f"(threshold {_fmt_threshold(g)}).",
            **{k: g[k] for k in ("guardrail_id", "metric_name", "variant_key", "observed", "threshold", "action")},
        )
    evaluated = [g for g in guardrails if g.get("status") != "no_data"]
    check(
        "guardrails_healthy", "Guardrails healthy", not breaches,
        f"{len(breaches)} of {len(evaluated)} guardrail checks breached." if evaluated else "No guardrails evaluated.",
    )

    # SRM
    srm = stats.get("srm")
    if srm:
        mismatch = srm.get("is_mismatch", False)
        detail = f"SRM p={srm.get('p_value')} ({'mismatch' if mismatch else 'balanced'})."
        if mismatch:
            evidence.add("srm", f"Sample ratio mismatch detected: observed {srm.get('observed_counts')}.",
                         p_value=srm.get("p_value"))
    else:
        mismatch = False
        detail = "No data for SRM check."
    check("srm_not_detected", "SRM not detected", not mismatch, detail)

    # Sample size
    needed = (stats.get("sample_size") or {}).get("recommended_per_variant", 0)
    min_users = min((v.get("unique_users", 0) for v in variants.values()), default=0)
    sufficient = bool(variants) and needed > 0 and min_users >= needed
    check(
        "sufficient_sample_size", "Sufficient sample size", sufficient,
        f"{min_users:,} users in smallest variant, {needed:,} needed." if variants else "No users yet.",
    )

    # Segments
    segments = (inputs.get("segments") or {}).get("segments") or []
    regressions = [s for s in segments if s.get("is_significant") and s.get("lift", 0) < 0]
    for s in regressions:
        evidence.add(
            "segment",
            f"Segment {s['dimension']}={s['value']} regressed {s['lift'] * 100:+.1f}% (p={s['p_value']:.4f}).",
            dimension=s["dimension"], value=s["value"], lift=s["lift"],
        )
    top = (inputs.get("segments") or {}).get("top_contributors") or []
    if top and not regressions:
        t = top[0]
        evidence.add(
            "segment",
            f"Segment {t['dimension']}={t['value']} drives {t['contribution_pct']}% of the effect "
            f"({t['lift'] * 100:+.1f}% lift).",
            **t,
        )
    check(
        "no_segment_regressions", "No significant segment regressions", not regressions,
        f"{len(regressions)} segment(s) significantly regressed." if segments else "No segment data provided.",
    )

    # Production telemetry
    impact = inputs.get("production_impact") or {}
    critical_metrics = []
    for variant_key, metrics in impact.items():
        for metric_name, m in metrics.items():
            if m.get("status") == "critical":
                critical_metrics.append((variant_key, metric_name, m))
                evidence.add(
                    "production",
                    f"{metric_name} for {variant_key} changed {m['change_pct']:+.1f}% vs control "
                    f"({m['control_avg']} → {m['variant_avg']}).",
                    variant=variant_key, metric=metric_name, change_pct=m["change_pct"],
                )
    check(
        "production_healthy", "Production telemetry healthy", not critical_metrics,
        f"{len(critical_metrics)} critical telemetry regression(s)." if impact else "No telemetry data.",
    )

    # Anomalies
    anomalies = inputs.get("anomalies") or []
    for a in anomalies:
        evidence.add(
            "anomaly",
            f"{a['severity'].title()} anomaly in {a['metric_name']} for {a['variant_key']} at {a['timestamp']}: "
            f"{a['value']} vs baseline {a['baseline_mean']}.",
            **{k: a.get(k) for k in ("variant_key", "metric_name", "timestamp", "value", "baseline_mean", "z_score")},
        )
    check("no_anomalies", "No telemetry anomalies", not anomalies, f"{len(anomalies)} anomaly(ies) detected.")

    # Health
    health = inputs.get("health") or {}
    score = health.get("overall_score")
    health_ok = score is None or score >= policy["min_health_score"]
    if score is not None:
        weakest = sorted((health.get("dimensions") or {}).items(), key=lambda kv: kv[1].get("score", 100))[:1]
        extra = f" Weakest: {weakest[0][0]} ({weakest[0][1].get('detail')})" if weakest and not health_ok else ""
        evidence.add("health", f"Experiment health score is {score}/100.{extra}", score=score)
    check(
        "health_score_ok", "Health score above minimum", health_ok,
        f"{score}/100 (minimum {policy['min_health_score']})." if score is not None else "Health not computed.",
    )

    # Interactions
    interactions = [i for i in inputs.get("interactions") or [] if i.get("is_interaction")]
    for i in interactions:
        evidence.add(
            "interaction",
            f"{i['interaction_type'].title()} interaction between {i['experiment_a']} and {i['experiment_b']} "
            f"({i['interaction_effect'] * 100:+.1f} pp vs additive).",
            experiment_a=i["experiment_a"], experiment_b=i["experiment_b"],
        )
    check(
        "no_interactions", "No experiment interactions", not interactions,
        f"{len(interactions)} interaction(s) detected." if interactions else "No interactions detected.",
    )

    return checks


# ── Helpers ──


def _significant_regressions(stats, control_key):
    variants = (stats or {}).get("variants") or {}
    return [
        (k, v) for k, v in variants.items()
        if k != control_key and v.get("is_significant") and (v.get("lift") or 0) < 0
    ]


def _best_significant_winner(stats, control_key):
    variants = (stats or {}).get("variants") or {}
    winners = [
        (k, v) for k, v in variants.items()
        if k != control_key and v.get("is_significant") and (v.get("lift") or 0) > 0
    ]
    return max(winners, key=lambda kv: kv[1]["lift"]) if winners else None


def _pct(basis_points):
    return f"{basis_points / 100:g}%"


def _fmt_observed(g):
    if g["operator"].startswith("RELATIVE"):
        return f"{g['observed']:+.1f}% vs control"
    return f"{g['observed']}"


def _fmt_threshold(g):
    if g["operator"].startswith("RELATIVE"):
        return f"{g['threshold']}%"
    return f"{g['threshold']}"


def harmful_anomalies(anomalies_by_metric, control_key="control"):
    """Keep only treatment-variant anomalies whose direction is harmful for the metric."""
    kept = []
    for metric_name, per_variant in anomalies_by_metric.items():
        direction = metric_direction(metric_name)
        for variant_key, anomalies in per_variant.items():
            if variant_key == control_key:
                continue
            for a in anomalies:
                z = a.get("z_score")
                up = a["value"] > a["baseline_mean"] if z is None else z > 0
                if direction == "up" and not up:
                    continue
                if direction == "down" and up:
                    continue
                kept.append({**a, "variant_key": variant_key, "metric_name": metric_name})
    return kept
