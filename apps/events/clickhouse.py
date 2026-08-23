import json
import logging

from django.conf import settings

logger = logging.getLogger(__name__)

_client = None


def get_clickhouse_client():
    """Lazy singleton ClickHouse client."""
    global _client
    if _client is not None:
        return _client

    host = getattr(settings, "CLICKHOUSE_HOST", "")
    if not host:
        return None

    try:
        import clickhouse_connect

        _client = clickhouse_connect.get_client(
            host=host,
            port=getattr(settings, "CLICKHOUSE_PORT", 8123),
            database=getattr(settings, "CLICKHOUSE_DATABASE", "experimentos"),
        )
        return _client
    except Exception:
        logger.warning("Failed to connect to ClickHouse", exc_info=True)
        return None


EXPOSURES_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS experiment_exposures (
    event_id String,
    user_id String,
    experiment_id String,
    experiment_key String,
    version_number UInt32,
    variant_key String,
    bucket UInt32,
    source String,
    event_time DateTime
) ENGINE = MergeTree()
ORDER BY (experiment_id, event_time)
"""

CONVERSIONS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS conversion_events (
    event_id String,
    user_id String,
    event_name String,
    value Float64,
    metadata String,
    event_time DateTime
) ENGINE = MergeTree()
ORDER BY (event_name, event_time)
"""


def ensure_schema():
    """Create ClickHouse tables if they don't exist."""
    client = get_clickhouse_client()
    if client is None:
        raise RuntimeError("Cannot connect to ClickHouse")

    client.command(EXPOSURES_TABLE_SQL)
    client.command(CONVERSIONS_TABLE_SQL)
    logger.info("ClickHouse schema ensured.")


def insert_exposure(event):
    """Insert a single exposure event into ClickHouse."""
    client = get_clickhouse_client()
    if client is None:
        logger.warning("ClickHouse not available, skipping exposure insert")
        return

    from datetime import datetime

    timestamp = event.get("timestamp", "")
    if isinstance(timestamp, str):
        # Parse ISO format, strip timezone info for ClickHouse DateTime
        try:
            dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
            event_time = dt.strftime("%Y-%m-%d %H:%M:%S")
        except (ValueError, TypeError):
            event_time = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    else:
        event_time = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")

    row = [[
        event["event_id"],
        event["user_id"],
        event.get("experiment_id", ""),
        event.get("experiment_key", ""),
        event.get("version_number", 0),
        event.get("variant_key", ""),
        event.get("bucket", 0),
        event.get("source", ""),
        event_time,
    ]]

    try:
        client.insert(
            "experiment_exposures",
            row,
            column_names=[
                "event_id", "user_id", "experiment_id", "experiment_key",
                "version_number", "variant_key", "bucket", "source", "event_time",
            ],
        )
    except Exception:
        logger.warning("Failed to insert exposure into ClickHouse", exc_info=True)


def insert_conversion(event):
    """Insert a single conversion event into ClickHouse."""
    client = get_clickhouse_client()
    if client is None:
        logger.warning("ClickHouse not available, skipping conversion insert")
        return

    from datetime import datetime

    timestamp = event.get("timestamp", "")
    if isinstance(timestamp, str):
        try:
            dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
            event_time = dt.strftime("%Y-%m-%d %H:%M:%S")
        except (ValueError, TypeError):
            event_time = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    else:
        event_time = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")

    metadata_str = json.dumps(event.get("metadata", {}))

    row = [[
        event["event_id"],
        event["user_id"],
        event.get("event_name", ""),
        float(event.get("value", 0.0)),
        metadata_str,
        event_time,
    ]]

    try:
        client.insert(
            "conversion_events",
            row,
            column_names=[
                "event_id", "user_id", "event_name", "value", "metadata", "event_time",
            ],
        )
    except Exception:
        logger.warning("Failed to insert conversion into ClickHouse", exc_info=True)


def query_experiment_results(experiment_id):
    """
    Query ClickHouse for per-variant exposure and conversion data.

    Returns dict with variant-level stats:
    {
        "variant_key": {
            "exposures": int,
            "unique_users": int,
            "conversions": int,
            "conversion_rate": float,
        }
    }
    """
    client = get_clickhouse_client()
    if client is None:
        return {}

    try:
        # Get per-variant exposure stats
        exposure_query = """
            SELECT
                variant_key,
                count() AS exposures,
                uniq(user_id) AS unique_users
            FROM experiment_exposures
            WHERE experiment_id = {experiment_id:String}
            GROUP BY variant_key
        """
        exposure_result = client.query(
            exposure_query,
            parameters={"experiment_id": str(experiment_id)},
        )

        variants = {}
        exposed_users_by_variant = {}

        for row in exposure_result.result_rows:
            variant_key = row[0]
            variants[variant_key] = {
                "exposures": row[1],
                "unique_users": row[2],
                "conversions": 0,
                "conversion_rate": 0.0,
            }

        # Get user_ids per variant for conversion join
        user_variant_query = """
            SELECT DISTINCT user_id, variant_key
            FROM experiment_exposures
            WHERE experiment_id = {experiment_id:String}
        """
        user_variant_result = client.query(
            user_variant_query,
            parameters={"experiment_id": str(experiment_id)},
        )

        for row in user_variant_result.result_rows:
            user_id, variant_key = row[0], row[1]
            exposed_users_by_variant.setdefault(variant_key, set()).add(user_id)

        if exposed_users_by_variant:
            # Get all conversions for exposed users
            all_exposed_users = set()
            for users in exposed_users_by_variant.values():
                all_exposed_users.update(users)

            if all_exposed_users:
                conversion_query = """
                    SELECT user_id, count() AS conversions
                    FROM conversion_events
                    WHERE user_id IN {user_ids:Array(String)}
                    GROUP BY user_id
                """
                conversion_result = client.query(
                    conversion_query,
                    parameters={"user_ids": list(all_exposed_users)},
                )

                user_conversions = {row[0]: row[1] for row in conversion_result.result_rows}

                for variant_key, users in exposed_users_by_variant.items():
                    variant_conversions = sum(
                        user_conversions.get(uid, 0) for uid in users
                    )
                    if variant_key in variants:
                        variants[variant_key]["conversions"] = variant_conversions
                        unique = variants[variant_key]["unique_users"]
                        if unique > 0:
                            variants[variant_key]["conversion_rate"] = round(
                                variant_conversions / unique, 4
                            )

        return variants

    except Exception:
        logger.warning("Failed to query experiment results from ClickHouse", exc_info=True)
        return {}
