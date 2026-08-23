from .base import *  # noqa: F401, F403

DEBUG = True

DATABASES = {
    "default": env.db("DATABASE_URL"),  # noqa: F405
}

CORS_ALLOW_ALL_ORIGINS = True
