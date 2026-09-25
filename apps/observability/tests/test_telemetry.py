import pytest
from unittest.mock import MagicMock, patch

from apps.observability.telemetry import (
    _classify_metric_status,
    analyze_production_impact,
    detect_anomalies,
    ingest_telemetry,
    query_variant_telemetry,
)


class TestClassifyMetricStatus:
    def test_latency_high_increase_critical(self):
        assert _classify_metric_status("latency_ms", 25.0) == "critical"

    def test_latency_moderate_increase_warning(self):
        assert _classify_metric_status("latency_ms", 15.0) == "warning"

    def test_latency_small_increase_healthy(self):
        assert _classify_metric_status("latency_ms", 5.0) == "healthy"

    def test_error_rate_high_critical(self):
        assert _classify_metric_status("error_rate", 30.0) == "critical"

    def test_error_rate_moderate_warning(self):
        assert _classify_metric_status("error_rate", 12.0) == "warning"

    def test_throughput_large_decrease_critical(self):
        assert _classify_metric_status("throughput_rps", -25.0) == "critical"

    def test_throughput_moderate_decrease_warning(self):
        assert _classify_metric_status("throughput_rps", -15.0) == "warning"

    def test_throughput_small_decrease_healthy(self):
        assert _classify_metric_status("throughput_rps", -5.0) == "healthy"

    def test_unknown_metric_healthy(self):
        assert _classify_metric_status("custom_metric", 50.0) == "healthy"

    def test_cpu_increase_critical(self):
        assert _classify_metric_status("cpu_usage", 25.0) == "critical"

    def test_availability_decrease_critical(self):
        assert _classify_metric_status("availability", -25.0) == "critical"


class TestAnalyzeProductionImpact:
    def test_empty_data_returns_empty(self):
        assert analyze_production_impact({}) == {}

    def test_single_variant_no_control(self):
        data = {
            "treatment": {
                "latency_ms": {"count": 100, "avg": 50.0, "p50": 45.0, "p95": 90.0, "p99": 100.0, "min": 10.0, "max": 120.0},
            }
        }
        # When no control exists, first variant becomes baseline, no comparisons returned
        result = analyze_production_impact(data)
        assert result == {}

    def test_control_vs_treatment(self):
        data = {
            "control": {
                "latency_ms": {"count": 1000, "avg": 100.0, "p50": 90.0, "p95": 180.0, "p99": 200.0, "min": 10.0, "max": 300.0},
            },
            "treatment": {
                "latency_ms": {"count": 1000, "avg": 120.0, "p50": 110.0, "p95": 200.0, "p99": 250.0, "min": 15.0, "max": 350.0},
            },
        }
        result = analyze_production_impact(data)
        assert "treatment" in result
        assert "latency_ms" in result["treatment"]
        impact = result["treatment"]["latency_ms"]
        assert impact["control_avg"] == 100.0
        assert impact["variant_avg"] == 120.0
        assert impact["change_pct"] == 20.0
        assert impact["status"] == "warning"

    def test_multiple_metrics(self):
        data = {
            "control": {
                "latency_ms": {"count": 100, "avg": 100.0, "p50": 90.0, "p95": 180.0, "p99": 200.0, "min": 10.0, "max": 300.0},
                "error_rate": {"count": 100, "avg": 0.01, "p50": 0.01, "p95": 0.02, "p99": 0.03, "min": 0.0, "max": 0.05},
            },
            "treatment": {
                "latency_ms": {"count": 100, "avg": 105.0, "p50": 95.0, "p95": 185.0, "p99": 210.0, "min": 12.0, "max": 310.0},
                "error_rate": {"count": 100, "avg": 0.015, "p50": 0.012, "p95": 0.025, "p99": 0.035, "min": 0.0, "max": 0.06},
            },
        }
        result = analyze_production_impact(data)
        assert len(result["treatment"]) == 2

    def test_zero_control_avg(self):
        data = {
            "control": {
                "errors": {"count": 100, "avg": 0.0, "p50": 0.0, "p95": 0.0, "p99": 0.0, "min": 0.0, "max": 0.0},
            },
            "treatment": {
                "errors": {"count": 100, "avg": 5.0, "p50": 3.0, "p95": 8.0, "p99": 10.0, "min": 0.0, "max": 12.0},
            },
        }
        result = analyze_production_impact(data)
        assert result["treatment"]["errors"]["change_pct"] == 0.0

    def test_custom_control_key(self):
        data = {
            "baseline": {
                "latency_ms": {"count": 100, "avg": 100.0, "p50": 90.0, "p95": 180.0, "p99": 200.0, "min": 10.0, "max": 300.0},
            },
            "variant_a": {
                "latency_ms": {"count": 100, "avg": 150.0, "p50": 140.0, "p95": 250.0, "p99": 280.0, "min": 20.0, "max": 400.0},
            },
        }
        result = analyze_production_impact(data, control_key="baseline")
        assert "variant_a" in result
        assert result["variant_a"]["latency_ms"]["change_pct"] == 50.0


class TestDetectAnomalies:
    def test_empty_data(self):
        assert detect_anomalies({}) == []

    def test_no_control_returns_empty(self):
        data = {"treatment": {"latency_ms": {"count": 100, "avg": 100.0}}}
        assert detect_anomalies(data) == []

    def test_detects_anomaly(self):
        data = {
            "control": {
                "latency_ms": {"count": 1000, "avg": 100.0, "p50": 90.0, "p95": 180.0, "p99": 200.0, "min": 10.0, "max": 300.0},
            },
            "treatment": {
                "latency_ms": {"count": 1000, "avg": 150.0, "p50": 140.0, "p95": 250.0, "p99": 280.0, "min": 20.0, "max": 400.0},
            },
        }
        anomalies = detect_anomalies(data, threshold_pct=20.0)
        assert len(anomalies) == 1
        assert anomalies[0]["variant_key"] == "treatment"
        assert anomalies[0]["metric_name"] == "latency_ms"
        assert anomalies[0]["deviation_pct"] == 50.0
        assert anomalies[0]["severity"] == "critical"

    def test_no_anomaly_below_threshold(self):
        data = {
            "control": {
                "latency_ms": {"count": 1000, "avg": 100.0, "p50": 90.0, "p95": 180.0, "p99": 200.0, "min": 10.0, "max": 300.0},
            },
            "treatment": {
                "latency_ms": {"count": 1000, "avg": 105.0, "p50": 95.0, "p95": 185.0, "p99": 210.0, "min": 12.0, "max": 310.0},
            },
        }
        anomalies = detect_anomalies(data, threshold_pct=20.0)
        assert len(anomalies) == 0

    def test_warning_severity(self):
        data = {
            "control": {
                "latency_ms": {"count": 1000, "avg": 100.0, "p50": 90.0, "p95": 180.0, "p99": 200.0, "min": 10.0, "max": 300.0},
            },
            "treatment": {
                "latency_ms": {"count": 1000, "avg": 125.0, "p50": 115.0, "p95": 210.0, "p99": 240.0, "min": 15.0, "max": 350.0},
            },
        }
        anomalies = detect_anomalies(data, threshold_pct=20.0)
        assert len(anomalies) == 1
        assert anomalies[0]["severity"] == "warning"

    def test_sorted_by_deviation(self):
        data = {
            "control": {
                "latency_ms": {"count": 100, "avg": 100.0},
                "error_rate": {"count": 100, "avg": 0.01},
            },
            "treatment": {
                "latency_ms": {"count": 100, "avg": 130.0},
                "error_rate": {"count": 100, "avg": 0.05},
            },
        }
        anomalies = detect_anomalies(data, threshold_pct=20.0)
        assert len(anomalies) == 2
        # error_rate has 400% deviation, latency has 30% — error_rate should be first
        assert anomalies[0]["metric_name"] == "error_rate"

    def test_zero_control_avg_skipped(self):
        data = {
            "control": {
                "errors": {"count": 100, "avg": 0.0},
            },
            "treatment": {
                "errors": {"count": 100, "avg": 5.0},
            },
        }
        anomalies = detect_anomalies(data, threshold_pct=20.0)
        assert len(anomalies) == 0


class TestIngestTelemetry:
    def test_ingest_basic(self, mock_clickhouse):
        ingest_telemetry("exp-1", "control", "latency_ms", 42.5)
        mock_clickhouse.insert.assert_called_once()

    def test_ingest_with_event_time(self, mock_clickhouse):
        ingest_telemetry("exp-1", "control", "latency_ms", 42.5, event_time="2024-01-15T10:30:00Z")
        mock_clickhouse.insert.assert_called_once()

    def test_ingest_with_invalid_time(self, mock_clickhouse):
        ingest_telemetry("exp-1", "control", "latency_ms", 42.5, event_time="not-a-date")
        mock_clickhouse.insert.assert_called_once()

    def test_ingest_clickhouse_unavailable(self):
        with patch("apps.observability.telemetry.get_clickhouse_client", return_value=None):
            # Should not raise
            ingest_telemetry("exp-1", "control", "latency_ms", 42.5)


class TestQueryVariantTelemetry:
    def test_query_returns_structured_data(self, mock_clickhouse):
        mock_clickhouse.query.return_value = MagicMock(result_rows=[
            ("control", "latency_ms", 1000, 50.1234, 45.0, 90.0, 100.0, 10.0, 200.0),
            ("treatment", "latency_ms", 1000, 55.5678, 50.0, 95.0, 110.0, 12.0, 220.0),
        ])
        result = query_variant_telemetry("exp-1")
        assert "control" in result
        assert "treatment" in result
        assert result["control"]["latency_ms"]["avg"] == 50.1234
        assert result["treatment"]["latency_ms"]["count"] == 1000

    def test_query_clickhouse_unavailable(self):
        with patch("apps.observability.telemetry.get_clickhouse_client", return_value=None):
            result = query_variant_telemetry("exp-1")
            assert result == {}

    def test_query_exception_returns_empty(self, mock_clickhouse):
        mock_clickhouse.query.side_effect = Exception("Connection refused")
        result = query_variant_telemetry("exp-1")
        assert result == {}
