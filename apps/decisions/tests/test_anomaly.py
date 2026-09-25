from apps.decisions.anomaly import detect_timeseries_anomalies, metric_direction


def _series(values):
    return [(f"t{i}", v) for i, v in enumerate(values)]


class TestDetectTimeseriesAnomalies:
    def test_plan_example_spike_detected(self):
        # 1.2%, 1.4%, 1.5%, 1.7% ... 5.8% <- anomaly
        values = [1.2, 1.4, 1.5, 1.3, 1.6, 1.4, 1.7, 5.8]
        anomalies = detect_timeseries_anomalies(_series(values))
        assert len(anomalies) == 1
        assert anomalies[0]["timestamp"] == "t7"
        assert anomalies[0]["value"] == 5.8
        assert anomalies[0]["severity"] == "critical"

    def test_stable_series_has_no_anomalies(self):
        values = [10, 11, 10, 9, 10, 11, 10, 9, 10, 11]
        assert detect_timeseries_anomalies(_series(values)) == []

    def test_not_enough_baseline(self):
        assert detect_timeseries_anomalies(_series([1, 1, 50])) == []

    def test_flat_baseline_jump(self):
        values = [2.0] * 6 + [4.0]
        anomalies = detect_timeseries_anomalies(_series(values))
        assert len(anomalies) == 1
        assert anomalies[0]["z_score"] is None

    def test_flat_baseline_small_change_ignored(self):
        values = [2.0] * 6 + [2.2]
        assert detect_timeseries_anomalies(_series(values)) == []

    def test_direction_filter(self):
        values = [10, 11, 10, 9, 10, 11, 10, 0.5]
        assert detect_timeseries_anomalies(_series(values), direction="up") == []
        assert len(detect_timeseries_anomalies(_series(values), direction="down")) == 1


class TestMetricDirection:
    def test_directions(self):
        assert metric_direction("error_rate") == "up"
        assert metric_direction("latency_ms_p95") == "up"
        assert metric_direction("throughput_rps") == "down"
        assert metric_direction("conversion") == "down"
        assert metric_direction("queue_depth") == "both"
