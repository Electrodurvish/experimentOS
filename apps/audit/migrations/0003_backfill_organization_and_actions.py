from django.db import migrations

LEGACY_ACTIONS = {
    "experiment_created": "EXPERIMENT_CREATED",
    "version_created": "VERSION_CREATED",
    "status_change": "STATUS_CHANGED",
    "rollout_changed": "ROLLOUT_CHANGED",
    "rollback_triggered": "ROLLBACK_TRIGGERED",
}


def forwards(apps, schema_editor):
    AuditLog = apps.get_model("audit", "AuditLog")
    for old, new in LEGACY_ACTIONS.items():
        AuditLog.objects.filter(action=old).update(action=new)
    for log in AuditLog.objects.filter(organization__isnull=True, experiment__isnull=False).select_related(
        "experiment__project"
    ):
        log.organization_id = log.experiment.project.organization_id
        log.save(update_fields=["organization"])


class Migration(migrations.Migration):
    dependencies = [
        ("audit", "0002_auditlog_organization_alter_auditlog_action_and_more"),
    ]

    operations = [migrations.RunPython(forwards, migrations.RunPython.noop)]
