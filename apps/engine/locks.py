import logging
import time
import uuid
from contextlib import contextmanager

import redis
from django.conf import settings

from apps.engine.cache import get_redis_client

logger = logging.getLogger(__name__)


class LockAcquisitionError(Exception):
    """Raised when a distributed lock cannot be acquired."""
    pass


# Lua script for atomic check-and-delete (release only if we own the lock)
RELEASE_SCRIPT = """
if redis.call("get", KEYS[1]) == ARGV[1] then
    return redis.call("del", KEYS[1])
else
    return 0
end
"""


@contextmanager
def distributed_lock(resource_name, ttl=None, retry_count=3, retry_delay=None):
    """
    Redis-based distributed lock using SET NX EX.

    Usage:
        with distributed_lock(f"experiment:{experiment_id}:transition"):
            # critical section
            ...

    Raises LockAcquisitionError if lock cannot be acquired after retries.
    """
    ttl = ttl or settings.REDIS_LOCK_TTL
    retry_delay = retry_delay or settings.REDIS_LOCK_RETRY_DELAY
    lock_key = f"lock:{resource_name}"
    lock_value = str(uuid.uuid4())
    client = get_redis_client()
    acquired = False

    for attempt in range(retry_count):
        try:
            acquired = client.set(lock_key, lock_value, nx=True, ex=ttl)
        except redis.RedisError:
            logger.warning("Redis lock acquisition failed", exc_info=True)
            break

        if acquired:
            break
        if attempt < retry_count - 1:
            time.sleep(retry_delay)

    if not acquired:
        raise LockAcquisitionError(
            f"Could not acquire lock on '{resource_name}' after {retry_count} attempts."
        )

    try:
        yield
    finally:
        try:
            # Release only if we still own the lock
            # Try Lua script first (atomic), fall back to get+delete
            try:
                client.eval(RELEASE_SCRIPT, 1, lock_key, lock_value)
            except (redis.exceptions.ResponseError, NotImplementedError):
                # Lua not supported (e.g., fakeredis) — use get+delete
                current = client.get(lock_key)
                if current == lock_value:
                    client.delete(lock_key)
        except redis.RedisError:
            logger.warning("Failed to release lock %s", lock_key, exc_info=True)
