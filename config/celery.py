"""
Celery application.

RabbitMQ is the broker: it carries jobs (evaluate experiments, recalculate
health, send alerts), while Kafka carries the high-volume event stream.
"""

import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.local")

app = Celery("experimentos")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()
