import json
from unittest.mock import MagicMock, patch

from apps.events.producer import produce_conversion, produce_exposure


class TestProduceExposure:
    def test_produces_exposure_event(self, mock_kafka):
        produce_exposure(
            user_id="user-100",
            experiment_id="exp-123",
            experiment_key="checkout_v3",
            version_number=1,
            variant_key="treatment",
            bucket=6721,
            source="computed",
        )

        mock_kafka.produce.assert_called_once()
        call_kwargs = mock_kafka.produce.call_args
        assert call_kwargs.kwargs["topic"] == "experiment-exposures"
        assert call_kwargs.kwargs["key"] == "user-100"

        payload = json.loads(call_kwargs.kwargs["value"])
        assert payload["event_type"] == "experiment_exposure"
        assert payload["user_id"] == "user-100"
        assert payload["experiment_id"] == "exp-123"
        assert payload["experiment_key"] == "checkout_v3"
        assert payload["version_number"] == 1
        assert payload["variant_key"] == "treatment"
        assert payload["bucket"] == 6721
        assert payload["source"] == "computed"
        assert "event_id" in payload
        assert "timestamp" in payload

    def test_produces_with_poll(self, mock_kafka):
        produce_exposure(
            user_id="user-100",
            experiment_id="exp-123",
            experiment_key="test",
            version_number=1,
            variant_key="control",
            bucket=100,
            source="sticky",
        )
        mock_kafka.poll.assert_called_once_with(0)

    def test_producer_failure_is_silent(self, mock_kafka):
        mock_kafka.produce.side_effect = Exception("Kafka down")
        # Should not raise
        produce_exposure(
            user_id="user-100",
            experiment_id="exp-123",
            experiment_key="test",
            version_number=1,
            variant_key="control",
            bucket=100,
            source="computed",
        )

    def test_disabled_producer_does_nothing(self):
        with patch("apps.events.producer._get_producer", return_value=None):
            produce_exposure(
                user_id="user-100",
                experiment_id="exp-123",
                experiment_key="test",
                version_number=1,
                variant_key="control",
                bucket=100,
                source="computed",
            )
            # No error, just silently skipped


class TestProduceConversion:
    def test_produces_conversion_event(self, mock_kafka):
        produce_conversion(
            user_id="user-200",
            event_name="purchase",
            value=49.99,
            metadata={"currency": "USD"},
            event_id="evt-456",
        )

        mock_kafka.produce.assert_called_once()
        call_kwargs = mock_kafka.produce.call_args
        assert call_kwargs.kwargs["topic"] == "conversion-events"
        assert call_kwargs.kwargs["key"] == "user-200"

        payload = json.loads(call_kwargs.kwargs["value"])
        assert payload["event_type"] == "purchase"
        assert payload["user_id"] == "user-200"
        assert payload["event_name"] == "purchase"
        assert payload["value"] == 49.99
        assert payload["metadata"] == {"currency": "USD"}
        assert payload["event_id"] == "evt-456"

    def test_conversion_auto_generates_event_id(self, mock_kafka):
        produce_conversion(user_id="user-100", event_name="signup")

        call_kwargs = mock_kafka.produce.call_args
        payload = json.loads(call_kwargs.kwargs["value"])
        assert len(payload["event_id"]) == 36  # UUID format

    def test_conversion_defaults(self, mock_kafka):
        produce_conversion(user_id="user-100", event_name="click")

        call_kwargs = mock_kafka.produce.call_args
        payload = json.loads(call_kwargs.kwargs["value"])
        assert payload["value"] == 0.0
        assert payload["metadata"] == {}
