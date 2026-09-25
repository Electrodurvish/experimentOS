import json
import logging

import redis
from django.conf import settings

from apps.observability.metrics import record_cache_hit, record_cache_miss, record_error

logger = logging.getLogger(__name__)

_pool = None


def get_redis_client():
    """Get a Redis client from the connection pool (singleton pool)."""
    global _pool
    if _pool is None:
        _pool = redis.ConnectionPool.from_url(
            settings.REDIS_URL,
            max_connections=20,
            decode_responses=True,
        )
    return redis.Redis(connection_pool=_pool)


# ── Cache Key Patterns ──


def _experiment_config_key(project_id, experiment_key):
    return f"exp:config:{project_id}:{experiment_key}"


def _active_experiments_key(project_id):
    return f"exp:active:{project_id}"


# ── Experiment Config Cache ──


def get_cached_experiment_config(project_id, experiment_key):
    """Retrieve cached experiment config. Returns None on miss or error."""
    try:
        client = get_redis_client()
        data = client.get(_experiment_config_key(project_id, experiment_key))
        if data:
            record_cache_hit()
            return json.loads(data)
    except redis.RedisError:
        logger.warning("Redis read failed for experiment config", exc_info=True)
        record_error("redis", "read_failed")
    record_cache_miss()
    return None


def cache_experiment_config(project_id, experiment_key, config):
    """Cache a serialized experiment config with TTL."""
    try:
        client = get_redis_client()
        client.setex(
            _experiment_config_key(project_id, experiment_key),
            settings.REDIS_EXPERIMENT_CACHE_TTL,
            json.dumps(config),
        )
    except redis.RedisError:
        logger.warning("Redis write failed for experiment config", exc_info=True)


def invalidate_experiment_config(project_id, experiment_key):
    """Delete cached config for a specific experiment."""
    try:
        client = get_redis_client()
        client.delete(_experiment_config_key(project_id, experiment_key))
    except redis.RedisError:
        logger.warning("Redis invalidation failed", exc_info=True)


def invalidate_project_experiments(project_id):
    """Delete all cached experiment configs for a project."""
    try:
        client = get_redis_client()
        pattern = f"exp:config:{project_id}:*"
        cursor = 0
        while True:
            cursor, keys = client.scan(cursor=cursor, match=pattern, count=100)
            if keys:
                client.delete(*keys)
            if cursor == 0:
                break
    except redis.RedisError:
        logger.warning("Redis project invalidation failed", exc_info=True)


def get_cached_active_experiments(project_id):
    """Get cached list of active experiment keys for a project."""
    try:
        client = get_redis_client()
        data = client.get(_active_experiments_key(project_id))
        if data:
            return json.loads(data)
    except redis.RedisError:
        logger.warning("Redis read failed for active experiments", exc_info=True)
    return None


def cache_active_experiments(project_id, experiment_keys):
    """Cache active experiment keys for a project."""
    try:
        client = get_redis_client()
        client.setex(
            _active_experiments_key(project_id),
            settings.REDIS_EXPERIMENT_CACHE_TTL,
            json.dumps(experiment_keys),
        )
    except redis.RedisError:
        logger.warning("Redis write failed for active experiments", exc_info=True)


def invalidate_active_experiments(project_id):
    """Invalidate active experiments list cache."""
    try:
        client = get_redis_client()
        client.delete(_active_experiments_key(project_id))
    except redis.RedisError:
        logger.warning("Redis invalidation failed", exc_info=True)


# ── Experiment Config Serialization ──


def serialize_experiment_config(experiment):
    """Serialize a Django Experiment ORM object to a cacheable dict."""
    version = experiment.current_version
    version_data = None

    if version:
        targeting = getattr(version, "targeting", None)
        version_data = {
            "id": str(version.id),
            "version_number": version.version_number,
            "traffic_allocation": version.traffic_allocation,
            "is_active": version.is_active,
            "targeting_rules": targeting.rules_json if targeting and targeting.rules_json else None,
            "variants": [
                {
                    "id": str(v.id),
                    "key": v.key,
                    "name": v.name,
                    "is_control": v.is_control,
                    "traffic_percentage": v.traffic_percentage,
                    "bucket_start": v.bucket_start,
                    "bucket_end": v.bucket_end,
                    "payload": v.payload,
                }
                for v in version.variants.all()
            ],
        }

    return {
        "id": str(experiment.id),
        "key": experiment.key,
        "status": experiment.status,
        "project_id": str(experiment.project_id),
        "current_version": version_data,
    }
