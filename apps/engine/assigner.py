import logging
from dataclasses import dataclass, field
from typing import Any

from apps.engine.evaluator import evaluate_rule
from apps.engine.hasher import compute_bucket, compute_rollout_bucket
from apps.engine.models import Assignment
from apps.engine.sticky import get_sticky_assignment, save_sticky_assignment
from apps.experiments.models import ExperimentStatus, ExperimentVersion, Variant

logger = logging.getLogger(__name__)


@dataclass
class EvaluationResult:
    assigned: bool
    variant_key: str | None = None
    variant_payload: dict = field(default_factory=dict)
    bucket: int | None = None
    version_number: int | None = None
    experiment_key: str | None = None
    reason: str = ""
    source: str = ""  # "sticky", "computed", or ""


@dataclass
class DebugStep:
    step: str
    passed: bool | None = None
    detail: str = ""


def evaluate_experiment(
    experiment,
    user_id: str,
    context: dict[str, Any],
    debug: bool = False,
    persist: bool = True,
) -> EvaluationResult | tuple[EvaluationResult, list[DebugStep]]:
    """
    Full evaluation pipeline:
    1. Check experiment is RUNNING
    2. Get current active version
    3. Evaluate targeting rules
    4. Check the live rollout gate
    5. Check Cassandra for sticky assignment
    6. If no sticky: compute bucket, check traffic, map variant
    7. Record assignment + persist sticky (skipped when persist=False, e.g. the debugger)
    """
    steps = [] if debug else None

    # Step 1: Status check
    if experiment.status != ExperimentStatus.RUNNING:
        result = EvaluationResult(
            assigned=False,
            experiment_key=experiment.key,
            reason="experiment_not_running",
        )
        if debug:
            steps.append(DebugStep(
                step="status_check",
                passed=False,
                detail=f"Experiment status is {experiment.status}, not RUNNING.",
            ))
            return result, steps
        return result

    if debug:
        steps.append(DebugStep(step="status_check", passed=True, detail="Experiment is RUNNING."))

    # Step 2: Get active version
    version = experiment.current_version
    if not version or not version.is_active:
        result = EvaluationResult(
            assigned=False,
            experiment_key=experiment.key,
            reason="no_active_version",
        )
        if debug:
            steps.append(DebugStep(step="version_check", passed=False, detail="No active version found."))
            return result, steps
        return result

    if debug:
        steps.append(DebugStep(
            step="version_check",
            passed=True,
            detail=f"Active version: v{version.version_number} (allocation: {version.traffic_allocation}).",
        ))

    # Step 3: Targeting
    targeting = getattr(version, "targeting", None)
    if targeting and targeting.rules_json:
        matched = evaluate_rule(targeting.rules_json, context)
        if not matched:
            result = EvaluationResult(
                assigned=False,
                experiment_key=experiment.key,
                version_number=version.version_number,
                reason="not_targeted",
            )
            if debug:
                steps.append(DebugStep(
                    step="targeting_check",
                    passed=False,
                    detail="User did not match targeting rules.",
                ))
                return result, steps
            return result
        if debug:
            steps.append(DebugStep(step="targeting_check", passed=True, detail="User matched targeting rules."))
    elif debug:
        steps.append(DebugStep(step="targeting_check", passed=True, detail="No targeting rules configured."))

    # Step 4: Live rollout gate (applies to sticky users too, so rollbacks take effect)
    rollout_percentage = getattr(experiment, "rollout_percentage", 10000)
    if rollout_percentage < 10000:
        rollout_bucket = compute_rollout_bucket(user_id, experiment.key)
        if rollout_bucket >= rollout_percentage:
            result = EvaluationResult(
                assigned=False,
                experiment_key=experiment.key,
                version_number=version.version_number,
                reason="rollout_excluded",
            )
            if debug:
                steps.append(DebugStep(
                    step="rollout_check",
                    passed=False,
                    detail=f"Rollout bucket {rollout_bucket} >= rollout {rollout_percentage / 100:g}%.",
                ))
                return result, steps
            return result
        if debug:
            steps.append(DebugStep(
                step="rollout_check",
                passed=True,
                detail=f"Rollout bucket {rollout_bucket} < rollout {rollout_percentage / 100:g}%.",
            ))
    elif debug:
        steps.append(DebugStep(step="rollout_check", passed=True, detail="Experiment is at 100% rollout."))

    # Step 5: Check Cassandra for sticky assignment
    sticky = get_sticky_assignment(user_id, str(experiment.id))

    if sticky:
        # Verify the sticky variant still exists in current version
        sticky_variant = _find_variant_by_key(version, sticky.variant_key)
        if sticky_variant:
            if debug:
                steps.append(DebugStep(
                    step="sticky_lookup",
                    passed=True,
                    detail=(
                        f"Sticky assignment found: {sticky.variant_key} "
                        f"(from v{sticky.version_number}, bucket {sticky.bucket})."
                    ),
                ))

            # Record in PostgreSQL for analytics
            if persist:
                _record_assignment(experiment, version, user_id, sticky_variant, sticky.bucket, context)

            result = EvaluationResult(
                assigned=True,
                variant_key=sticky.variant_key,
                variant_payload=sticky_variant.payload,
                bucket=sticky.bucket,
                version_number=version.version_number,
                experiment_key=experiment.key,
                reason="assigned",
                source="sticky",
            )
            if debug:
                return result, steps
            return result
        elif debug:
            steps.append(DebugStep(
                step="sticky_lookup",
                passed=False,
                detail=(
                    f"Sticky assignment found for variant '{sticky.variant_key}' "
                    f"but variant no longer exists in current version. Recomputing."
                ),
            ))
    elif debug:
        steps.append(DebugStep(
            step="sticky_lookup",
            passed=False,
            detail="No sticky assignment found. Computing fresh assignment.",
        ))

    # Step 6: Compute bucket
    bucket = compute_bucket(user_id, experiment.key, version.version_number)
    if debug:
        steps.append(DebugStep(
            step="bucket_computation",
            detail=f"hash('{user_id}:{experiment.key}:{version.version_number}') → bucket {bucket}",
        ))

    # Step 7: Traffic allocation check
    if bucket >= version.traffic_allocation:
        result = EvaluationResult(
            assigned=False,
            experiment_key=experiment.key,
            version_number=version.version_number,
            bucket=bucket,
            reason="traffic_excluded",
        )
        if debug:
            steps.append(DebugStep(
                step="traffic_check",
                passed=False,
                detail=f"Bucket {bucket} >= allocation {version.traffic_allocation}.",
            ))
            return result, steps
        return result

    if debug:
        steps.append(DebugStep(
            step="traffic_check",
            passed=True,
            detail=f"Bucket {bucket} < allocation {version.traffic_allocation}.",
        ))

    # Step 8: Find variant
    variant = _find_variant_for_bucket(version, bucket)
    if not variant:
        result = EvaluationResult(
            assigned=False,
            experiment_key=experiment.key,
            version_number=version.version_number,
            bucket=bucket,
            reason="no_variant_match",
        )
        if debug:
            steps.append(DebugStep(step="variant_assignment", passed=False, detail="No variant matched bucket."))
            return result, steps
        return result

    if debug:
        steps.append(DebugStep(
            step="variant_assignment",
            passed=True,
            detail=f"Bucket {bucket} → {variant.key} (range {variant.bucket_start}-{variant.bucket_end}).",
        ))

    # Step 9: Record assignment in PostgreSQL + Cassandra
    if persist:
        _record_assignment(experiment, version, user_id, variant, bucket, context)

        save_sticky_assignment(
            user_id=user_id,
            experiment_id=str(experiment.id),
            variant_key=variant.key,
            variant_payload=variant.payload,
            bucket=bucket,
            version_number=version.version_number,
        )

    result = EvaluationResult(
        assigned=True,
        variant_key=variant.key,
        variant_payload=variant.payload,
        bucket=bucket,
        version_number=version.version_number,
        experiment_key=experiment.key,
        reason="assigned",
        source="computed",
    )

    if debug:
        return result, steps
    return result


def _find_variant_for_bucket(version: ExperimentVersion, bucket: int) -> Variant | None:
    for variant in version.variants.all():
        if variant.bucket_start <= bucket <= variant.bucket_end:
            return variant
    return None


def _find_variant_by_key(version, variant_key):
    """Find a variant by key in a version's variants."""
    for variant in version.variants.all():
        if variant.key == variant_key:
            return variant
    return None


def _record_assignment(experiment, version, user_id, variant, bucket, context):
    """
    Record assignment in PostgreSQL. Uses raw IDs because on cache hits the
    experiment/version/variant are lightweight stand-ins, not ORM instances.
    """
    try:
        Assignment.objects.update_or_create(
            user_id=user_id,
            experiment_id=experiment.id,
            version_id=version.id,
            defaults={
                "variant_id": variant.id,
                "bucket": bucket,
                "context": context,
            },
        )
    except Exception:
        logger.warning("Failed to record assignment in PostgreSQL", exc_info=True)
