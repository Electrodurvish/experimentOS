"""Kubernetes probes."""

from django.db import connection
from django.http import JsonResponse


def healthz(request):
    """Liveness: the process is up and serving requests. No dependency checks."""
    return JsonResponse({"status": "ok"})


def readyz(request):
    """Readiness: PostgreSQL (source of truth for configuration) is reachable."""
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
    except Exception:
        return JsonResponse({"status": "unavailable", "database": "down"}, status=503)
    return JsonResponse({"status": "ok", "database": "up"})
