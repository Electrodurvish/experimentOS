import pytest
from unittest.mock import MagicMock, patch

from apps.observability.tracing import add_experiment_attributes, get_tracer, setup_tracing


class TestSetupTracing:
    def test_disabled_by_default(self, settings):
        settings.OTEL_ENABLED = False
        # Should not raise, just return
        setup_tracing()

    def test_enabled_initializes(self, settings):
        settings.OTEL_ENABLED = True
        settings.OTEL_SERVICE_NAME = "test-service"
        settings.OTEL_EXPORTER_OTLP_ENDPOINT = "http://localhost:4317"

        mock_trace = MagicMock()
        mock_provider_cls = MagicMock()
        mock_exporter_cls = MagicMock()
        mock_processor_cls = MagicMock()
        mock_resource = MagicMock()

        with patch.dict("sys.modules", {
            "opentelemetry": MagicMock(trace=mock_trace),
            "opentelemetry.trace": mock_trace,
            "opentelemetry.exporter.otlp.proto.grpc.trace_exporter": MagicMock(OTLPSpanExporter=mock_exporter_cls),
            "opentelemetry.sdk.resources": MagicMock(Resource=mock_resource),
            "opentelemetry.sdk.trace": MagicMock(TracerProvider=mock_provider_cls),
            "opentelemetry.sdk.trace.export": MagicMock(BatchSpanProcessor=mock_processor_cls),
        }):
            setup_tracing()
            mock_trace.set_tracer_provider.assert_called_once()

    def test_import_failure_handled(self, settings):
        settings.OTEL_ENABLED = True
        with patch.dict("sys.modules", {"opentelemetry": None}):
            # Should not raise
            setup_tracing()


class TestGetTracer:
    def test_returns_tracer(self):
        import apps.observability.tracing as t
        t._tracer = None
        mock_trace = MagicMock()
        mock_trace.get_tracer.return_value = MagicMock()
        with patch.dict("sys.modules", {
            "opentelemetry": MagicMock(trace=mock_trace),
            "opentelemetry.trace": mock_trace,
        }):
            # Force re-import inside get_tracer
            tracer = get_tracer("test")
            assert tracer is not None
        t._tracer = None  # cleanup

    def test_returns_cached_tracer(self):
        import apps.observability.tracing as t
        mock_tracer = MagicMock()
        t._tracer = mock_tracer
        result = get_tracer()
        assert result is mock_tracer
        t._tracer = None  # cleanup


class TestAddExperimentAttributes:
    def test_adds_all_attributes(self):
        span = MagicMock()
        add_experiment_attributes(
            span,
            experiment_id="exp-1",
            experiment_key="checkout_v3",
            variant="treatment",
            version=1,
            bucket=4567,
        )
        assert span.set_attribute.call_count == 5

    def test_adds_partial_attributes(self):
        span = MagicMock()
        add_experiment_attributes(span, experiment_id="exp-1")
        span.set_attribute.assert_called_once_with("experiment.id", "exp-1")

    def test_none_span_no_error(self):
        # Should not raise
        add_experiment_attributes(None, experiment_id="exp-1")

    def test_exception_suppressed(self):
        span = MagicMock()
        span.set_attribute.side_effect = Exception("boom")
        # Should not raise
        add_experiment_attributes(span, experiment_id="exp-1")


class TestExperimentSpan:
    def test_span_gets_attributes(self):
        from apps.observability import tracing

        span = MagicMock()
        tracer = MagicMock()
        tracer.start_as_current_span.return_value.__enter__.return_value = span
        with patch.object(tracing, "get_tracer", return_value=tracer):
            with tracing.experiment_span("experiment.evaluate", experiment_key="checkout_v3") as s:
                assert s is span
        tracer.start_as_current_span.assert_called_once_with("experiment.evaluate")
        span.set_attribute.assert_any_call("experiment.key", "checkout_v3")

    def test_span_without_tracer(self):
        from apps.observability import tracing

        with patch.object(tracing, "get_tracer", return_value=None):
            with tracing.experiment_span("x") as s:
                assert s is None
