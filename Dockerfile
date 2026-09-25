# syntax=docker/dockerfile:1.7
#
# ExperimentOS backend image (api, event-consumer, celery-worker, celery-beat).
#
# One image, several processes: the default CMD runs gunicorn; Kubernetes and
# docker-compose override the command for the consumer / celery processes.
#
#   docker build -t experimentos-api .
#   docker build --build-arg INSTALL_DEV=true -t experimentos-api:dev .   # + pytest, ruff
#
# poetry.lock is gitignored in this repo, so the build must work without it:
# if no lock file is in the build context, `poetry install` resolves the
# dependency ranges from pyproject.toml (slower, and not bit-for-bit
# reproducible). If a lock file is present it is used as-is.

ARG PYTHON_VERSION=3.12

# ---------------------------------------------------------------------------
# Stage 1: build the virtualenv
# ---------------------------------------------------------------------------
FROM python:${PYTHON_VERSION}-slim AS builder

ARG POETRY_VERSION=1.8.3
ARG INSTALL_DEV=false

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    POETRY_NO_INTERACTION=1 \
    POETRY_VIRTUALENVS_CREATE=false \
    VIRTUAL_ENV=/opt/venv \
    PATH=/opt/venv/bin:$PATH

# Compilers only live in the builder stage (for any sdist without a wheel,
# e.g. cassandra-driver C extensions on some platforms).
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*

# Poetry gets its own venv so its dependencies never leak into the app venv.
RUN python -m venv /opt/poetry \
    && /opt/poetry/bin/pip install "poetry==${POETRY_VERSION}" \
    && python -m venv /opt/venv

WORKDIR /build
COPY pyproject.toml poetry.lock* ./

# With VIRTUAL_ENV set and virtualenvs.create=false, Poetry installs into /opt/venv.
RUN --mount=type=cache,target=/root/.cache/pypoetry \
    if [ "$INSTALL_DEV" = "true" ]; then GROUPS_ARG="--with dev"; else GROUPS_ARG="--only main"; fi \
    && /opt/poetry/bin/poetry install --no-root --no-ansi $GROUPS_ARG

# ---------------------------------------------------------------------------
# Stage 2: runtime
# ---------------------------------------------------------------------------
FROM python:${PYTHON_VERSION}-slim AS runtime

ARG APP_UID=10001
ARG APP_GID=10001

LABEL org.opencontainers.image.title="experimentos-api" \
      org.opencontainers.image.description="ExperimentOS Django backend (api / consumer / celery)" \
      org.opencontainers.image.source="https://github.com/Electrodurvish/experimentOS"

# gunicorn reads extra CLI args from GUNICORN_CMD_ARGS; override per environment.
# One worker + threads by default: Prometheus metrics are per-process (no
# multiprocess mode yet), so several workers would each expose partial counters.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    VIRTUAL_ENV=/opt/venv \
    PATH=/opt/venv/bin:$PATH \
    DJANGO_SETTINGS_MODULE=config.settings.production \
    GUNICORN_CMD_ARGS="--bind 0.0.0.0:8000 --workers 1 --threads 8 --worker-class gthread --timeout 30 --graceful-timeout 25 --access-logfile - --error-logfile -"

RUN groupadd --system --gid ${APP_GID} app \
    && useradd --system --uid ${APP_UID} --gid app --home-dir /app --shell /usr/sbin/nologin app

COPY --from=builder /opt/venv /opt/venv

WORKDIR /app
COPY --chown=app:app . .

# collectstatic needs importable settings; production settings require these
# env vars, so give it throwaway values that exist only for this RUN step.
RUN SECRET_KEY=collectstatic-only \
    DATABASE_URL=sqlite:////tmp/collectstatic.sqlite3 \
    ALLOWED_HOSTS=localhost \
    python manage.py collectstatic --noinput \
    && rm -f /tmp/collectstatic.sqlite3 \
    && chown -R app:app /app/staticfiles

USER app:app

EXPOSE 8000 9100

CMD ["gunicorn", "config.wsgi:application"]
