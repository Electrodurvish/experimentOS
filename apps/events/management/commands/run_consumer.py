from django.core.management.base import BaseCommand

from apps.events.consumer import run_consumer


class Command(BaseCommand):
    help = "Run the Kafka event consumer (long-running process)"

    def handle(self, *args, **options):
        self.stdout.write("Starting Kafka event consumer...")
        run_consumer()
