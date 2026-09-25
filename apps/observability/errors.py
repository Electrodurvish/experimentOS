"""
Sentry error tracking.

Enabled only when SENTRY_DSN is set. Every captured error is tagged with
the experiment context of the current request (see tag_experiment), so
crashes can be grouped by experiment and variant.
"""

import logging

from django.conf import settings

logger = logging.getLogger(__name__)


def setup_sentry():
    """Initialize the Sentry SDK. Call once at startup."""
    dsn = getattr(settings, "SENTRY_DSN", "")
    if not dsn:
        return False

    try:
        import sentry_sdk
        from sentry_sdk.integrations.celery import CeleryIntegration
        from sentry_sdk.integrations.django import DjangoIntegration

        sentry_sdk.init(
            dsn=dsn,
            environment=getattr(settings, "SENTRY_ENVIRONMENT", "development"),
            traces_sample_rate=getattr(settings, "SENTRY_TRACES_SAMPLE_RATE", 0.0),
            integrations=[DjangoIntegration(), CeleryIntegration()],
            send_default_pii=False,
        )
        logger.info("Sentry initialized")
        return True
    except Exception:
        logger.warning("Failed to initialize Sentry", exc_info=True)
        return False


def tag_experiment(experiment_key, variant_key=None, version=None):
    """Attach experiment context to the current Sentry scope (no-op without Sentry)."""
    try:
        import sentry_sdk

        sentry_sdk.set_tag("experiment.key", experiment_key)
        if variant_key:
            sentry_sdk.set_tag("experiment.variant", variant_key)
        if version is not None:
            sentry_sdk.set_tag("experiment.version", str(version))
    except Exception:
        pass
