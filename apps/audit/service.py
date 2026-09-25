from apps.audit.context import get_client_ip
from apps.audit.models import AuditLog


def record_audit(action, *, experiment=None, organization=None, actor=None,
                 old_value=None, new_value=None, metadata=None):
    """Create an audit entry. The organization is derived from the experiment when not given."""
    if organization is None and experiment is not None:
        organization_id = experiment.project.organization_id
    else:
        organization_id = organization.id if organization is not None else None
    if actor is not None and not getattr(actor, "is_authenticated", False):
        actor = None
    return AuditLog.objects.create(
        experiment=experiment,
        organization_id=organization_id,
        actor=actor,
        action=action,
        old_value=old_value,
        new_value=new_value,
        metadata=metadata or {},
        ip_address=get_client_ip(),
    )
