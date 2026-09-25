"""
Evidence bundles for the AI layer.

The AI never sees raw databases: it receives a numbered list of evidence
statements built from the platform's own engines (statistics, health,
guardrails, telemetry, anomalies, decisions, rollout history, timeline) and
must cite those IDs in its answer. That keeps explanations grounded in data
the platform can show the user.
"""

from apps.decisions.context import gather_inputs
from apps.decisions.engine import decide
from apps.engine.models import Assignment


def build_experiment_evidence(experiment, segments=None):
    """
    Returns:
        {
            "experiment": {...config summary...},
            "decision": {recommendation, confidence_label, summary},
            "evidence": [{"id": "E1", "kind": str, "statement": str, "data": {...}}, ...],
        }
    """
    inputs = gather_inputs(experiment, segments=segments)
    result = decide(inputs)
    evidence = list(result.evidence)

    def add(kind, statement, **data):
        evidence.append({"id": f"E{len(evidence) + 1}", "kind": kind, "statement": statement, "data": data})

    add("decision", f"Decision engine recommends {result.recommendation} "
                    f"({result.confidence_label} confidence): {result.summary}",
        recommendation=result.recommendation, confidence=result.confidence)

    for key, v in (inputs["stats"].get("variants") or {}).items():
        statement = (
            f"Variant {key}: {v.get('unique_users', 0):,} users, conversion rate "
            f"{v.get('conversion_rate', 0) * 100:.2f}% (95% CI {v.get('ci_lower', 0) * 100:.2f}–"
            f"{v.get('ci_upper', 0) * 100:.2f}%)"
        )
        if v.get("lift") is not None:
            statement += f", lift {v['lift'] * 100:+.1f}% vs control (p={v['p_value']:.4f})"
        add("results", statement + ".", variant=key)

    for m in inputs.get("metrics") or []:
        for key, v in m["variants"].items():
            if v.get("lift") is None:
                continue
            add("metric", f"{m['metric_type'].title()} metric \"{m['name']}\" for {key}: {v['value']} "
                          f"({v['lift'] * 100:+.1f}% vs control, p={v['p_value']:.4f}).",
                metric=m["name"], variant=key)

    for c in experiment.rollout_changes.all()[:10]:
        add("rollout", f"{c.created_at:%Y-%m-%d %H:%M} UTC: rollout {c.action} {c.from_percentage / 100:g}% → "
                       f"{c.to_percentage / 100:g}% ({'automated' if c.automated else 'manual'}): {c.reason}",
            action=c.action, at=c.created_at.isoformat())

    for d in experiment.decisions.exclude(applied_action="")[:5]:
        add("decision_history", f"{d.created_at:%Y-%m-%d %H:%M} UTC: decision {d.recommendation} applied "
                                f"({d.applied_action}): {d.summary}", at=d.created_at.isoformat())

    for t in experiment.timeline_events.order_by("-created_at")[:15]:
        add("timeline", f"{t.created_at:%Y-%m-%d %H:%M} UTC: {t.title}" + (f" — {t.detail}" if t.detail else ""),
            event_type=t.event_type, at=t.created_at.isoformat())

    assigned = Assignment.objects.filter(experiment=experiment).count()
    if assigned:
        add("assignments", f"{assigned:,} assignments recorded in PostgreSQL for this experiment.", count=assigned)

    version = experiment.current_version
    return {
        "experiment": {
            "id": str(experiment.id),
            "key": experiment.key,
            "name": experiment.name,
            "hypothesis": experiment.hypothesis,
            "status": experiment.status,
            "rollout_percentage": experiment.rollout_percentage / 100,
            "version": version.version_number if version else None,
            "variants": [v.key for v in version.variants.all()] if version else [],
            "started_at": experiment.started_at.isoformat() if experiment.started_at else None,
        },
        "decision": {
            "recommendation": result.recommendation,
            "confidence_label": result.confidence_label,
            "summary": result.summary,
        },
        "evidence": evidence,
    }


def build_portfolio_evidence(experiments):
    """Compact evidence for questions across many experiments (uses persisted decisions, no live queries)."""
    rows = []
    for exp in experiments:
        latest = exp.decisions.first()
        rows.append({
            "id": str(exp.id),
            "key": exp.key,
            "name": exp.name,
            "status": exp.status,
            "rollout_percentage": exp.rollout_percentage / 100,
            "latest_decision": {
                "recommendation": latest.recommendation,
                "confidence_label": latest.confidence_label,
                "summary": latest.summary,
                "at": latest.created_at.isoformat(),
            } if latest else None,
            "rollbacks": exp.rollout_changes.filter(action="rollback").count(),
        })
    return rows
