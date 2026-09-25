from rest_framework.throttling import AnonRateThrottle, SimpleRateThrottle


class APIKeyRateThrottle(SimpleRateThrottle):
    """
    Rate limit SDK traffic per API key (falls back to client IP when no key is sent).
    Counters live in the shared Redis cache, so the limit holds across API pods.
    """

    scope = "sdk"

    def get_cache_key(self, request, view):
        api_key = request.auth
        ident = f"key:{api_key.pk}" if getattr(api_key, "pk", None) else f"ip:{self.get_ident(request)}"
        return self.cache_format % {"scope": self.scope, "ident": ident}


class AuthRateThrottle(AnonRateThrottle):
    """Brute-force protection for login and registration, per client IP."""

    scope = "auth"
