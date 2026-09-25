import sys
import time

from django.conf import settings
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Exit non-zero if the event consumer loop has not written its heartbeat recently (liveness probe)."

    def add_arguments(self, parser):
        parser.add_argument("--max-age", type=float, default=90.0, help="Maximum heartbeat age in seconds.")

    def handle(self, *args, **options):
        path = settings.CONSUMER_HEARTBEAT_FILE
        try:
            with open(path) as f:
                age = time.time() - float(f.read().strip())
        except (OSError, ValueError):
            self.stderr.write(f"No heartbeat at {path}")
            sys.exit(1)
        if age > options["max_age"]:
            self.stderr.write(f"Heartbeat is {age:.0f}s old (max {options['max_age']:.0f}s)")
            sys.exit(1)
        self.stdout.write(f"ok ({age:.1f}s)")
