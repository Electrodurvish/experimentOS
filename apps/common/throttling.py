"""
Rate limiting.

Throttle counters live in the Redis-backed Django cache so limits hold across
API pods. Every throttle here fails open: if the cache is unreachable the
request is allowed and the error is counted, so a Redis outage degrades rate
limiting instead of turning the evaluation hot path into 500s.
"""

import logging

from rest_framework.throttling import AnonRateThrottle, ScopedRateThrottle, SimpleRateThrottle, UserRateThrottle

from apps.observability.metrics import record_error

logger = logging.getLogger(__name__)


class FailOpenMixin:
    def allow_request(self, request, view):
        try:
            return super().allow_request(request, view)
        except Exception:
            logger.warning("Throttle cache unavailable; allowing request", exc_info=True)
            record_error("throttle", "cache_unavailable")
            return True


class APIKeyRateThrottle(FailOpenMixin, SimpleRateThrottle):
    """Rate limit SDK traffic per API key (falls back to client IP when no key is sent)."""

    scope = "sdk"

    def get_cache_key(self, request, view):
        api_key = request.auth
        ident = f"key:{api_key.pk}" if getattr(api_key, "pk", None) else f"ip:{self.get_ident(request)}"
        return self.cache_format % {"scope": self.scope, "ident": ident}


class AuthRateThrottle(FailOpenMixin, AnonRateThrottle):
    """Brute-force protection for login and registration, per client IP."""

    scope = "auth"


class FailOpenUserRateThrottle(FailOpenMixin, UserRateThrottle):
    pass


class FailOpenScopedRateThrottle(FailOpenMixin, ScopedRateThrottle):
    pass
