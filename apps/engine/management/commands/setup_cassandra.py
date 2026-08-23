from django.core.management.base import BaseCommand

from apps.engine.sticky import ensure_schema


class Command(BaseCommand):
    help = "Create Cassandra keyspace and tables for sticky bucketing"

    def handle(self, *args, **options):
        self.stdout.write("Setting up Cassandra schema...")
        ensure_schema()
        self.stdout.write(self.style.SUCCESS("Cassandra schema setup complete."))
