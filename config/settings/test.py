import os

os.environ.setdefault("SECRET_KEY", "test-secret-key")
os.environ.setdefault("DEBUG", "True")
os.environ.setdefault("ALLOWED_HOSTS", "localhost,127.0.0.1")
os.environ.setdefault("DATABASE_URL", "sqlite:///test.sqlite3")

from .base import *  # noqa: F401, F403, E402

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    },
}

PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.MD5PasswordHasher",
]

# Disable Cassandra in tests (will be mocked)
CASSANDRA_STICKY_ENABLED = False

# Disable Kafka in tests (will be mocked)
KAFKA_ENABLED = False

# Disable ClickHouse in tests (will be mocked)
CLICKHOUSE_HOST = ""
CLICKHOUSE_DATABASE = "test_experimentos"

# Run Celery tasks inline in tests
CELERY_TASK_ALWAYS_EAGER = True
CELERY_BROKER_URL = "memory://"
