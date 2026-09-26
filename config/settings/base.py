from datetime import timedelta
from pathlib import Path

import environ

BASE_DIR = Path(__file__).resolve().parent.parent.parent

env = environ.Env(
    DEBUG=(bool, False),
    ALLOWED_HOSTS=(list, []),
)

SECRET_KEY = env("SECRET_KEY")
DEBUG = env("DEBUG")
ALLOWED_HOSTS = env("ALLOWED_HOSTS")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Third party
    "rest_framework",
    "django_filters",
    "drf_spectacular",
    "corsheaders",
    # Local apps
    "apps.common",
    "apps.accounts",
    "apps.organizations",
    "apps.experiments",
    "apps.engine",
    "apps.audit",
    "apps.events",
    "apps.stats",
    "apps.intelligence",
    "apps.observability.apps.ObservabilityConfig",
    "apps.decisions.apps.DecisionsConfig",
    "apps.ai.apps.AIConfig",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "apps.observability.middleware.MetricsMiddleware",
    "apps.audit.context.AuditContextMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

AUTH_USER_MODEL = "accounts.User"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# DRF
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework_simplejwt.authentication.JWTAuthentication",
        "apps.accounts.authentication.APIKeyAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
        "apps.organizations.permissions.OrganizationRolePermission",
    ],
    "DEFAULT_FILTER_BACKENDS": [
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework.filters.SearchFilter",
        "rest_framework.filters.OrderingFilter",
    ],
    "DEFAULT_PAGINATION_CLASS": "apps.common.pagination.StandardPagination",
    "PAGE_SIZE": 20,
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "EXCEPTION_HANDLER": "apps.common.exceptions.custom_exception_handler",
    "DEFAULT_THROTTLE_CLASSES": [
        "apps.common.throttling.FailOpenUserRateThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {
        "user": env("USER_THROTTLE_RATE", default="1200/min"),
        "ai": env("AI_THROTTLE_RATE", default="30/min"),
        "sdk": env("SDK_THROTTLE_RATE", default="6000/min"),
        "auth": env("AUTH_THROTTLE_RATE", default="20/min"),
    },
}

# SimpleJWT
SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=30),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=7),
    "AUTH_HEADER_TYPES": ("Bearer",),
}

# drf-spectacular
SPECTACULAR_SETTINGS = {
    "TITLE": "ExperimentOS API",
    "DESCRIPTION": "Intelligent Experimentation & Release Platform",
    "VERSION": "1.0.0",
    "COMPONENT_SPLIT_REQUEST": True,
}

# CORS
CORS_ALLOW_ALL_ORIGINS = False
CORS_ALLOWED_ORIGINS = env.list("CORS_ALLOWED_ORIGINS", default=[])

# Redis (direct redis-py)
REDIS_URL = env("REDIS_URL", default="redis://localhost:6379/0")
# Django cache (throttling / rate limiting state shared across API pods)
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": REDIS_URL,
        "OPTIONS": {"socket_connect_timeout": 0.5, "socket_timeout": 0.5},
    },
}
REDIS_EXPERIMENT_CACHE_TTL = 300  # 5 minutes
REDIS_SOCKET_TIMEOUT = env.float("REDIS_SOCKET_TIMEOUT", default=0.25)  # seconds; fail fast on partitions
REDIS_LOCK_TTL = 30  # 30 seconds for distributed locks
REDIS_LOCK_RETRY_DELAY = 0.1  # 100ms retry

# Cassandra (sticky bucketing)
CASSANDRA_CONTACT_POINTS = env.list("CASSANDRA_CONTACT_POINTS", default=["localhost"])
CASSANDRA_PORT = env.int("CASSANDRA_PORT", default=9042)
CASSANDRA_KEYSPACE = env("CASSANDRA_KEYSPACE", default="experimentos")
CASSANDRA_LOCAL_DC = env("CASSANDRA_LOCAL_DC", default="")
CASSANDRA_CONNECT_TIMEOUT = env.float("CASSANDRA_CONNECT_TIMEOUT", default=5.0)
CASSANDRA_STICKY_ENABLED = env.bool("CASSANDRA_STICKY_ENABLED", default=True)

# Kafka
KAFKA_BOOTSTRAP_SERVERS = env("KAFKA_BOOTSTRAP_SERVERS", default="localhost:9092")
KAFKA_ENABLED = env.bool("KAFKA_ENABLED", default=True)
KAFKA_TOPIC_PARTITIONS = env.int("KAFKA_TOPIC_PARTITIONS", default=6)
KAFKA_REPLICATION_FACTOR = env.int("KAFKA_REPLICATION_FACTOR", default=1)

# ClickHouse
CLICKHOUSE_HOST = env("CLICKHOUSE_HOST", default="localhost")
CLICKHOUSE_PORT = env.int("CLICKHOUSE_PORT", default=8123)
CLICKHOUSE_DATABASE = env("CLICKHOUSE_DATABASE", default="experimentos")

# Event deduplication
EVENT_DEDUP_TTL = 86400  # 24 hours

# OpenTelemetry
OTEL_ENABLED = env.bool("OTEL_ENABLED", default=False)
OTEL_SERVICE_NAME = env("OTEL_SERVICE_NAME", default="experimentos-api")
OTEL_EXPORTER_OTLP_ENDPOINT = env("OTEL_EXPORTER_OTLP_ENDPOINT", default="http://localhost:4317")

# Prometheus port for the standalone Kafka consumer process (0 = disabled)
CONSUMER_METRICS_PORT = env.int("CONSUMER_METRICS_PORT", default=0)
# Liveness heartbeat written by the consumer loop (checked by `manage.py consumer_healthcheck`)
CONSUMER_HEARTBEAT_FILE = env("CONSUMER_HEARTBEAT_FILE", default="/tmp/consumer-heartbeat")

# Sentry
SENTRY_DSN = env("SENTRY_DSN", default="")
SENTRY_ENVIRONMENT = env("SENTRY_ENVIRONMENT", default="development")
SENTRY_TRACES_SAMPLE_RATE = env.float("SENTRY_TRACES_SAMPLE_RATE", default=0.0)

# Celery (RabbitMQ broker)
CELERY_BROKER_URL = env("CELERY_BROKER_URL", default="amqp://guest:guest@localhost:5672//")
CELERY_TASK_IGNORE_RESULT = True
CELERY_TASK_ACKS_LATE = True
CELERY_WORKER_PREFETCH_MULTIPLIER = 1
CELERY_TASK_ALWAYS_EAGER = env.bool("CELERY_TASK_ALWAYS_EAGER", default=False)
CELERY_BEAT_SCHEDULE = {
    "beat-heartbeat": {
        "task": "apps.decisions.tasks.beat_heartbeat",
        "schedule": 60,
    },
    "evaluate-running-experiments": {
        "task": "apps.decisions.tasks.evaluate_running_experiments",
        "schedule": env.int("DECISION_INTERVAL_SECONDS", default=300),
    },
    "recalculate-health-scores": {
        "task": "apps.decisions.tasks.recalculate_health_scores",
        "schedule": env.int("HEALTH_INTERVAL_SECONDS", default=900),
    },
}

# Alerts (automated rollbacks / pauses). Slack-compatible incoming webhook.
ALERT_WEBHOOK_URL = env("ALERT_WEBHOOK_URL", default="")

# AI layer (explanations over structured evidence)
ANTHROPIC_API_KEY = env("ANTHROPIC_API_KEY", default="")
AI_ENABLED = env.bool("AI_ENABLED", default=True)
AI_MODEL = env("AI_MODEL", default="claude-opus-5")
AI_EFFORT = env("AI_EFFORT", default="medium")
AI_TIMEOUT_SECONDS = env.float("AI_TIMEOUT_SECONDS", default=60.0)
