"""Request context for audit logging (client IP), set by AuditContextMiddleware."""

from contextvars import ContextVar

_client_ip: ContextVar[str | None] = ContextVar("audit_client_ip", default=None)


def get_client_ip():
    return _client_ip.get()


class AuditContextMiddleware:
    """
    Captures the client IP for the duration of the request. Uses the first
    X-Forwarded-For hop when present (the ingress sets it), else REMOTE_ADDR.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
        ip = forwarded.split(",")[0].strip() if forwarded else request.META.get("REMOTE_ADDR")
        token = _client_ip.set(ip or None)
        try:
            return self.get_response(request)
        finally:
            _client_ip.reset(token)
