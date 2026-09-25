"""
Automatic anomaly detection on production telemetry time series.

For each point we compare against a trailing baseline window:

    1.2%  1.4%  1.5%  1.7%  5.8%  <- anomaly (z-score far above baseline)

A point is anomalous when its z-score against the trailing window exceeds
the threshold. When the baseline is perfectly flat (std = 0) a relative
deviation check is used instead, so a jump from a constant value is still
caught.
"""

import math

DEFAULT_WINDOW = 12
DEFAULT_Z_THRESHOLD = 3.0
DEFAULT_MIN_BASELINE = 5
FLAT_BASELINE_RELATIVE_THRESHOLD = 0.5


def detect_timeseries_anomalies(
    points,
    window=DEFAULT_WINDOW,
    z_threshold=DEFAULT_Z_THRESHOLD,
    min_baseline=DEFAULT_MIN_BASELINE,
    direction="both",
):
    """
    Args:
        points: list of (timestamp, value), ordered by time.
        window: number of trailing points used as the baseline.
        z_threshold: |z| above which a point is anomalous.
        min_baseline: minimum trailing points before a point can be judged.
        direction: "up" (only increases are bad), "down", or "both".

    Returns list of dicts:
        {"timestamp", "value", "baseline_mean", "baseline_std", "z_score", "severity"}
    """
    anomalies = []
    values = [float(v) for _, v in points]

    for i in range(min_baseline, len(values)):
        baseline = values[max(0, i - window):i]
        if len(baseline) < min_baseline:
            continue

        mean = sum(baseline) / len(baseline)
        variance = sum((b - mean) ** 2 for b in baseline) / len(baseline)
        std = math.sqrt(variance)
        value = values[i]

        if std > 0:
            z = (value - mean) / std
            is_anomaly = abs(z) >= z_threshold
        else:
            if mean == 0:
                z = math.inf if value != 0 else 0.0
                is_anomaly = value != 0
            else:
                relative = (value - mean) / abs(mean)
                z = math.copysign(math.inf, relative) if relative else 0.0
                is_anomaly = abs(relative) >= FLAT_BASELINE_RELATIVE_THRESHOLD

        if not is_anomaly:
            continue
        if direction == "up" and z <= 0:
            continue
        if direction == "down" and z >= 0:
            continue

        anomalies.append({
            "timestamp": points[i][0],
            "value": round(value, 6),
            "baseline_mean": round(mean, 6),
            "baseline_std": round(std, 6),
            "z_score": round(z, 2) if math.isfinite(z) else None,
            "severity": "critical" if not math.isfinite(z) or abs(z) >= z_threshold * 2 else "warning",
        })

    return anomalies


def metric_direction(metric_name):
    """Which direction of change is harmful for a metric."""
    name = metric_name.lower()
    if any(m in name for m in ("throughput", "rps", "availability", "success", "conversion", "revenue")):
        return "down"
    if any(m in name for m in ("latency", "error", "crash", "cpu", "memory", "p95", "p99")):
        return "up"
    return "both"
