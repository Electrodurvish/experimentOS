"""
Production Telemetry Correlation Engine.

Correlates experiment variants with production health metrics:
- Latency (p50, p95, p99)
- Error rate
- Throughput

This prevents declaring a variant "winner" when it damages production.

Example output:
    Treatment
    Conversion     +12.4%   ✓
    Revenue         +8.2%   ✓
    Latency        +43.0%   ⚠
    Errors         +17.0%   ⚠

Telemetry data is ingested via API and stored in ClickHouse.
"""

import logging

from apps.events.clickhouse import get_clickhouse_client

logger = logging.getLogger(__name__)

# ClickHouse table for production telemetry
TELEMETRY_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS production_telemetry (
    experiment_id String,
    variant_key String,
    metric_name String,
    metric_value Float64,
    event_time DateTime
) ENGINE = MergeTree()
ORDER BY (experiment_id, variant_key, metric_name, event_time)
"""


def ensure_telemetry_schema():
    """Create the telemetry ClickHouse table."""
    client = get_clickhouse_client()
    if client is None:
        raise RuntimeError("Cannot connect to ClickHouse")
    client.command(TELEMETRY_TABLE_SQL)


def ingest_telemetry(experiment_id, variant_key, metric_name, metric_value, event_time=None):
    """
    Ingest a single production telemetry data point.

    Args:
        experiment_id: experiment UUID
        variant_key: which variant this metric is for
        metric_name: e.g., "latency_ms", "error_rate", "throughput_rps"
        metric_value: numeric value
        event_time: optional datetime string (ISO format)
    """
    client = get_clickhouse_client()
    if client is None:
        logger.warning("ClickHouse not available, skipping telemetry ingest")
        return

    from datetime import datetime, timezone

    if event_time and isinstance(event_time, str):
        try:
            dt = datetime.fromisoformat(event_time.replace("Z", "+00:00"))
            ts = dt.strftime("%Y-%m-%d %H:%M:%S")
        except (ValueError, TypeError):
            ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    else:
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

    try:
        client.insert(
            "production_telemetry",
            [[str(experiment_id), variant_key, metric_name, float(metric_value), ts]],
            column_names=["experiment_id", "variant_key", "metric_name", "metric_value", "event_time"],
        )
    except Exception:
        logger.warning("Failed to ingest telemetry", exc_info=True)


def query_variant_telemetry(experiment_id):
    """
    Query per-variant production telemetry summary.

    Returns:
        {
            "variant_key": {
                "metric_name": {
                    "count": int,
                    "avg": float,
                    "p50": float,
                    "p95": float,
                    "p99": float,
                    "min": float,
                    "max": float,
                }
            }
        }
    """
    client = get_clickhouse_client()
    if client is None:
        return {}

    try:
        query = """
            SELECT
                variant_key,
                metric_name,
                count() AS cnt,
                avg(metric_value) AS avg_val,
                quantile(0.5)(metric_value) AS p50,
                quantile(0.95)(metric_value) AS p95,
                quantile(0.99)(metric_value) AS p99,
                min(metric_value) AS min_val,
                max(metric_value) AS max_val
            FROM production_telemetry
            WHERE experiment_id = {experiment_id:String}
            GROUP BY variant_key, metric_name
            ORDER BY variant_key, metric_name
        """
        result = client.query(query, parameters={"experiment_id": str(experiment_id)})

        variants = {}
        for row in result.result_rows:
            variant_key = row[0]
            metric_name = row[1]

            if variant_key not in variants:
                variants[variant_key] = {}

            variants[variant_key][metric_name] = {
                "count": row[2],
                "avg": round(row[3], 4),
                "p50": round(row[4], 4),
                "p95": round(row[5], 4),
                "p99": round(row[6], 4),
                "min": round(row[7], 4),
                "max": round(row[8], 4),
            }

        return variants

    except Exception:
        logger.warning("Failed to query variant telemetry", exc_info=True)
        return {}


def analyze_production_impact(telemetry_data, control_key="control"):
    """
    Analyze production impact by comparing variant telemetry to control.

    Args:
        telemetry_data: output from query_variant_telemetry()
        control_key: which variant is the control

    Returns:
        {
            "variant_key": {
                "metric_name": {
                    "control_avg": float,
                    "variant_avg": float,
                    "change_pct": float,
                    "status": "healthy" | "warning" | "critical",
                }
            }
        }
    """
    if not telemetry_data:
        return {}

    control = telemetry_data.get(control_key, {})
    if not control:
        # Use first variant as baseline
        control_key = next(iter(telemetry_data))
        control = telemetry_data[control_key]

    impact = {}

    for variant_key, metrics in telemetry_data.items():
        if variant_key == control_key:
            continue

        variant_impact = {}

        for metric_name, stats in metrics.items():
            control_stats = control.get(metric_name, {})
            control_avg = control_stats.get("avg", 0)
            variant_avg = stats.get("avg", 0)

            if control_avg > 0:
                change_pct = round((variant_avg - control_avg) / control_avg * 100, 2)
            else:
                change_pct = 0.0

            # Determine status based on metric type
            status = _classify_metric_status(metric_name, change_pct)

            variant_impact[metric_name] = {
                "control_avg": control_avg,
                "variant_avg": variant_avg,
                "change_pct": change_pct,
                "status": status,
            }

        impact[variant_key] = variant_impact

    return impact


def _classify_metric_status(metric_name, change_pct):
    """
    Classify a metric change as healthy/warning/critical.

    For latency and error metrics, increases are bad.
    For throughput, decreases are bad.
    """
    metric_lower = metric_name.lower()

    # Metrics where increase is bad
    bad_increase_metrics = ["latency", "error", "crash", "cpu", "memory", "p95", "p99"]
    # Metrics where decrease is bad
    bad_decrease_metrics = ["throughput", "rps", "availability", "success"]

    is_bad_increase = any(m in metric_lower for m in bad_increase_metrics)
    is_bad_decrease = any(m in metric_lower for m in bad_decrease_metrics)

    if is_bad_increase:
        if change_pct > 20:
            return "critical"
        elif change_pct > 10:
            return "warning"
        else:
            return "healthy"
    elif is_bad_decrease:
        if change_pct < -20:
            return "critical"
        elif change_pct < -10:
            return "warning"
        else:
            return "healthy"
    else:
        return "healthy"


def detect_anomalies(telemetry_data, control_key="control", threshold_pct=20.0):
    """
    Detect anomalous metrics where variant significantly deviates from control.

    Returns list of anomaly dicts:
        [
            {
                "variant_key": str,
                "metric_name": str,
                "control_avg": float,
                "variant_avg": float,
                "deviation_pct": float,
                "severity": "warning" | "critical",
            }
        ]
    """
    if not telemetry_data:
        return []

    control = telemetry_data.get(control_key, {})
    if not control:
        return []

    anomalies = []

    for variant_key, metrics in telemetry_data.items():
        if variant_key == control_key:
            continue

        for metric_name, stats in metrics.items():
            control_stats = control.get(metric_name, {})
            control_avg = control_stats.get("avg", 0)
            variant_avg = stats.get("avg", 0)

            if control_avg == 0:
                continue

            deviation = abs((variant_avg - control_avg) / control_avg * 100)

            if deviation >= threshold_pct:
                severity = "critical" if deviation >= threshold_pct * 2 else "warning"
                anomalies.append({
                    "variant_key": variant_key,
                    "metric_name": metric_name,
                    "control_avg": control_avg,
                    "variant_avg": variant_avg,
                    "deviation_pct": round(deviation, 2),
                    "severity": severity,
                })

    # Sort by deviation (highest first)
    anomalies.sort(key=lambda a: a["deviation_pct"], reverse=True)
    return anomalies
