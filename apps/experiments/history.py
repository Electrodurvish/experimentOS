"""
Time-travel reconstruction of an experiment.

Versions are immutable once running, rollout changes and status transitions are
recorded, so the effective configuration at any past instant can be rebuilt:

    What configuration was active when this user was assigned?
"""

from apps.audit.models import AuditAction, AuditLog
from apps.experiments.models import ExperimentStatus

STATUS_ACTIONS = [
    AuditAction.EXPERIMENT_STARTED, AuditAction.EXPERIMENT_PAUSED, AuditAction.EXPERIMENT_RESUMED,
    AuditAction.EXPERIMENT_COMPLETED, AuditAction.EXPERIMENT_ARCHIVED, AuditAction.STATUS_CHANGED,
]


def version_config(version):
    if version is None:
        return None
    targeting = getattr(version, "targeting", None)
    return {
        "version_number": version.version_number,
        "traffic_allocation": version.traffic_allocation,
        "created_at": version.created_at.isoformat(),
        "targeting": targeting.rules_json if targeting else None,
        "variants": [
            {
                "key": v.key,
                "is_control": v.is_control,
                "traffic_percentage": v.traffic_percentage,
                "bucket_start": v.bucket_start,
                "bucket_end": v.bucket_end,
                "payload": v.payload,
            }
            for v in version.variants.all()
        ],
    }


def version_at(experiment, at):
    """The version that was current at `at`: each new version becomes current when created."""
    return (
        experiment.versions.filter(created_at__lte=at)
        .prefetch_related("variants")
        .select_related("targeting")
        .order_by("-version_number")
        .first()
    )


def rollout_at(experiment, at):
    before = experiment.rollout_changes.filter(created_at__lte=at).order_by("-created_at").first()
    if before:
        return before.to_percentage
    after = experiment.rollout_changes.filter(created_at__gt=at).order_by("created_at").first()
    return after.from_percentage if after else experiment.rollout_percentage


def status_at(experiment, at):
    logs = AuditLog.objects.filter(experiment=experiment, action__in=STATUS_ACTIONS)
    before = logs.filter(created_at__lte=at).order_by("-created_at").first()
    if before:
        return before.new_value.get("status")
    after = logs.filter(created_at__gt=at).order_by("created_at").first()
    if after:
        return (after.old_value or {}).get("status", ExperimentStatus.DRAFT)
    return experiment.status


def experiment_at(experiment, at):
    """Reconstruct status, rollout and configuration of `experiment` at datetime `at`."""
    if at < experiment.created_at:
        return None
    return {
        "at": at.isoformat(),
        "status": status_at(experiment, at),
        "rollout_percentage": rollout_at(experiment, at),
        "version": version_config(version_at(experiment, at)),
    }
