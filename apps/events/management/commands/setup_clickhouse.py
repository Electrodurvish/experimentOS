from django.core.management.base import BaseCommand

from apps.events.clickhouse import ensure_schema
from apps.observability.telemetry import ensure_telemetry_schema


class Command(BaseCommand):
    help = "Create ClickHouse tables for experiment events and production telemetry"

    def handle(self, *args, **options):
        self.stdout.write("Creating ClickHouse tables...")
        ensure_schema()
        ensure_telemetry_schema()
        self.stdout.write(self.style.SUCCESS("ClickHouse tables created successfully."))
