"""
Observability middleware.

Automatically records request latency and adds trace context
with experiment information to every request span.
"""

import time

from apps.observability.metrics import record_request


class MetricsMiddleware:
    """Records HTTP request latency and count for Prometheus."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        start = time.perf_counter()
        response = self.get_response(request)
        duration = time.perf_counter() - start

        # Use a simplified endpoint path for cardinality control
        endpoint = self._normalize_path(request.path)
        record_request(
            method=request.method,
            endpoint=endpoint,
            status_code=response.status_code,
            duration=duration,
        )

        return response

    @staticmethod
    def _normalize_path(path):
        """
        Normalize URL path to reduce metric cardinality.
        Replaces UUIDs and numeric IDs with placeholders.
        """
        import re
        # Replace UUIDs
        path = re.sub(
            r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
            "{id}",
            path,
        )
        # Replace numeric IDs
        path = re.sub(r"/\d+/", "/{id}/", path)
        return path
