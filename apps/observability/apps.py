from django.apps import AppConfig


class ObservabilityConfig(AppConfig):
    name = "apps.observability"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self):
        from apps.observability.errors import setup_sentry
        from apps.observability.tracing import instrument_django, setup_tracing

        setup_tracing()
        instrument_django()
        setup_sentry()
