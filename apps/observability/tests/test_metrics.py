import pytest
from unittest.mock import MagicMock, patch

from apps.observability.metrics import (
    _init_metrics,
    record_assignment,
    record_cache_hit,
    record_cache_miss,
    record_error,
    record_evaluation,
    record_event_produced,
    record_request,
)


@pytest.fixture(autouse=True)
def reset_metrics():
    """Reset metrics state between tests."""
    import apps.observability.metrics as m
    m._metrics_initialized = False
    m.REQUEST_LATENCY = None
    m.REQUEST_COUNT = None
    m.EVALUATION_LATENCY = None
    m.EVALUATION_COUNT = None
    m.ASSIGNMENT_COUNT = None
    m.CACHE_HIT_COUNT = None
    m.CACHE_MISS_COUNT = None
    m.EVENT_PRODUCED_COUNT = None
    m.ERROR_COUNT = None
    yield


class TestRecordRequest:
    def test_record_request_initializes_and_records(self):
        with patch("apps.observability.metrics.Histogram", create=True) as MockHist, \
             patch("apps.observability.metrics.Counter", create=True) as MockCounter:
            # Simulate prometheus_client available
            mock_hist = MagicMock()
            mock_counter = MagicMock()

            import apps.observability.metrics as m
            m._metrics_initialized = True
            m.REQUEST_LATENCY = mock_hist
            m.REQUEST_COUNT = mock_counter

            record_request("GET", "/api/v1/test", 200, 0.05)
            mock_hist.labels.assert_called_once()
            mock_counter.labels.assert_called_once()

    def test_record_request_no_metrics(self):
        # Should not raise when metrics are None
        record_request("GET", "/api/v1/test", 200, 0.05)


class TestRecordEvaluation:
    def test_record_evaluation(self):
        import apps.observability.metrics as m
        mock_hist = MagicMock()
        mock_counter = MagicMock()
        m._metrics_initialized = True
        m.EVALUATION_LATENCY = mock_hist
        m.EVALUATION_COUNT = mock_counter

        record_evaluation("exp-key", "assigned", 0.01)
        mock_hist.labels.assert_called_once_with(experiment_key="exp-key")
        mock_counter.labels.assert_called_once_with(experiment_key="exp-key", result="assigned")


class TestRecordAssignment:
    def test_record_assignment(self):
        import apps.observability.metrics as m
        mock_counter = MagicMock()
        m._metrics_initialized = True
        m.ASSIGNMENT_COUNT = mock_counter

        record_assignment("exp-key", "treatment")
        mock_counter.labels.assert_called_once_with(experiment_key="exp-key", variant_key="treatment")


class TestRecordCacheOps:
    def test_record_cache_hit(self):
        import apps.observability.metrics as m
        mock_counter = MagicMock()
        m._metrics_initialized = True
        m.CACHE_HIT_COUNT = mock_counter

        record_cache_hit()
        mock_counter.inc.assert_called_once()

    def test_record_cache_miss(self):
        import apps.observability.metrics as m
        mock_counter = MagicMock()
        m._metrics_initialized = True
        m.CACHE_MISS_COUNT = mock_counter

        record_cache_miss()
        mock_counter.inc.assert_called_once()


class TestRecordEventProduced:
    def test_record_event_produced(self):
        import apps.observability.metrics as m
        mock_counter = MagicMock()
        m._metrics_initialized = True
        m.EVENT_PRODUCED_COUNT = mock_counter

        record_event_produced("experiment-exposures")
        mock_counter.labels.assert_called_once_with(topic="experiment-exposures")


class TestRecordError:
    def test_record_error(self):
        import apps.observability.metrics as m
        mock_counter = MagicMock()
        m._metrics_initialized = True
        m.ERROR_COUNT = mock_counter

        record_error("engine", "ValueError")
        mock_counter.labels.assert_called_once_with(component="engine", error_type="ValueError")
