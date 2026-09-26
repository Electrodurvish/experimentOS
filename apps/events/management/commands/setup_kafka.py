from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.events.producer import TOPIC_CONVERSIONS, TOPIC_EXPOSURES


class Command(BaseCommand):
    help = (
        "Create the Kafka topics (and their .dlq topics) with enough partitions for the "
        "consumer group to scale out. Broker auto-creation would make single-partition topics."
    )

    def add_arguments(self, parser):
        parser.add_argument("--partitions", type=int, default=settings.KAFKA_TOPIC_PARTITIONS)
        parser.add_argument("--replication-factor", type=int, default=settings.KAFKA_REPLICATION_FACTOR)

    def handle(self, *args, **options):
        from confluent_kafka.admin import AdminClient, NewTopic

        admin = AdminClient({"bootstrap.servers": settings.KAFKA_BOOTSTRAP_SERVERS})
        existing = set(admin.list_topics(timeout=15).topics)
        wanted = []
        for topic in (TOPIC_EXPOSURES, TOPIC_CONVERSIONS):
            for name, partitions in ((topic, options["partitions"]), (f"{topic}.dlq", 1)):
                if name not in existing:
                    wanted.append(NewTopic(name, num_partitions=partitions,
                                           replication_factor=options["replication_factor"]))
        if not wanted:
            self.stdout.write("Kafka topics already exist.")
            return
        for name, future in admin.create_topics(wanted).items():
            try:
                future.result(timeout=30)
                self.stdout.write(f"Created topic {name}")
            except Exception as exc:
                if "TOPIC_ALREADY_EXISTS" not in str(exc):
                    raise CommandError(f"Could not create {name}: {exc}") from exc
        self.stdout.write(self.style.SUCCESS("Kafka topics ready."))
