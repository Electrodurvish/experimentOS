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


class EventStoreError(Exception):
    """ClickHouse is unavailable or rejected an insert; the event must be retried."""


def parse_event_time(value):
    """
    Normalize an event timestamp to a naive UTC datetime, which is what
    clickhouse-connect expects for DateTime columns (strings are rejected).
    Accepts ISO-8601 strings (with or without offset / trailing Z) and datetimes;
    anything unparseable becomes "now".
    """
    from datetime import datetime, timezone

    if isinstance(value, str) and value:
        try:
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            value = None
    if not isinstance(value, datetime):
        return datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0)
    if value.tzinfo is not None:
        value = value.astimezone(timezone.utc).replace(tzinfo=None)
    return value.replace(microsecond=0)


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
    """Insert a single exposure event into ClickHouse. Raises EventStoreError on failure."""
    client = get_clickhouse_client()
    if client is None:
        raise EventStoreError("ClickHouse not available")

    event_time = parse_event_time(event.get("timestamp"))

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
    except Exception as exc:
        raise EventStoreError(f"Failed to insert exposure: {exc}") from exc


def insert_conversion(event):
    """Insert a single conversion event into ClickHouse. Raises EventStoreError on failure."""
    client = get_clickhouse_client()
    if client is None:
        raise EventStoreError("ClickHouse not available")

    event_time = parse_event_time(event.get("timestamp"))

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
    except Exception as exc:
        raise EventStoreError(f"Failed to insert conversion: {exc}") from exc


RESULTS_QUERY = """
    SELECT
        e.variant_key,
        sum(e.exposures) AS exposures,
        count() AS unique_users,
        countIf(c.last_conversion >= e.first_exposure) AS conversions
    FROM (
        SELECT
            user_id,
            argMin(variant_key, event_time) AS variant_key,
            min(event_time) AS first_exposure,
            count() AS exposures
        FROM experiment_exposures
        WHERE experiment_id = {experiment_id:String}
        GROUP BY user_id
    ) AS e
    LEFT JOIN (
        SELECT user_id, max(event_time) AS last_conversion
        FROM conversion_events
        WHERE user_id IN (
            SELECT DISTINCT user_id FROM experiment_exposures WHERE experiment_id = {experiment_id:String}
        )
          AND ({event_name:String} = '' OR event_name = {event_name:String})
        GROUP BY user_id
    ) AS c USING (user_id)
    GROUP BY e.variant_key
"""


def _primary_event_name(experiment_id):
    from apps.stats.models import ExperimentMetric, MetricType

    return (
        ExperimentMetric.objects.filter(experiment_id=experiment_id, metric_type=MetricType.PRIMARY)
        .values_list("event_name", flat=True)
        .first()
    )


def query_experiment_results(experiment_id, event_name=None):
    """
    Per-variant exposure and conversion data, computed entirely in ClickHouse.

    - A user belongs to the variant of their first exposure (argMin by time).
    - A user converts if they have a conversion event at or after their first
      exposure. When the experiment has a PRIMARY metric only that event_name
      counts; otherwise any conversion event does.
    - "conversions" counts converting users, so conversion_rate is a proportion.

    Returns:
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

    if event_name is None:
        event_name = _primary_event_name(experiment_id) or ""

    try:
        result = client.query(
            RESULTS_QUERY,
            parameters={"experiment_id": str(experiment_id), "event_name": event_name},
        )
    except Exception:
        logger.warning("Failed to query experiment results from ClickHouse", exc_info=True)
        return {}

    variants = {}
    for variant_key, exposures, unique_users, conversions in result.result_rows:
        variants[variant_key] = {
            "exposures": exposures,
            "unique_users": unique_users,
            "conversions": conversions,
            "conversion_rate": round(conversions / unique_users, 4) if unique_users else 0.0,
        }
    return variants
