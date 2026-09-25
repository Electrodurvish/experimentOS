
from apps.events.consumer import is_duplicate, process_conversion, process_exposure


class TestDeduplication:
    def test_new_event_is_not_duplicate(self, fake_redis):
        assert is_duplicate("evt-001") is False

    def test_same_event_is_duplicate(self, fake_redis):
        assert is_duplicate("evt-002") is False
        assert is_duplicate("evt-002") is True

    def test_different_events_not_duplicate(self, fake_redis):
        assert is_duplicate("evt-003") is False
        assert is_duplicate("evt-004") is False

    def test_dedup_key_stored_in_redis(self, fake_redis):
        is_duplicate("evt-005")
        assert fake_redis.exists("dedup:evt-005")


class TestProcessExposure:
    def test_processes_valid_exposure(self, fake_redis, mock_clickhouse):
        event = {
            "event_id": "evt-100",
            "user_id": "user-1",
            "experiment_id": "exp-1",
            "experiment_key": "test",
            "version_number": 1,
            "variant_key": "control",
            "bucket": 500,
            "source": "computed",
            "timestamp": "2026-08-18T14:32:11+00:00",
        }
        process_exposure(event)
        mock_clickhouse.insert.assert_called_once()

    def test_skips_duplicate_exposure(self, fake_redis, mock_clickhouse):
        event = {
            "event_id": "evt-101",
            "user_id": "user-1",
            "experiment_id": "exp-1",
            "experiment_key": "test",
            "version_number": 1,
            "variant_key": "control",
            "bucket": 500,
            "source": "computed",
            "timestamp": "2026-08-18T14:32:11+00:00",
        }
        process_exposure(event)
        process_exposure(event)  # duplicate
        assert mock_clickhouse.insert.call_count == 1

    def test_skips_event_without_id(self, fake_redis, mock_clickhouse):
        event = {"user_id": "user-1", "experiment_id": "exp-1"}
        process_exposure(event)
        mock_clickhouse.insert.assert_not_called()


class TestProcessConversion:
    def test_processes_valid_conversion(self, fake_redis, mock_clickhouse):
        event = {
            "event_id": "evt-200",
            "user_id": "user-1",
            "event_name": "purchase",
            "value": 49.99,
            "metadata": {"currency": "USD"},
            "timestamp": "2026-08-18T14:35:22+00:00",
        }
        process_conversion(event)
        mock_clickhouse.insert.assert_called_once()

    def test_skips_duplicate_conversion(self, fake_redis, mock_clickhouse):
        event = {
            "event_id": "evt-201",
            "user_id": "user-1",
            "event_name": "purchase",
            "value": 10.0,
            "metadata": {},
            "timestamp": "2026-08-18T14:35:22+00:00",
        }
        process_conversion(event)
        process_conversion(event)  # duplicate
        assert mock_clickhouse.insert.call_count == 1

    def test_skips_conversion_without_id(self, fake_redis, mock_clickhouse):
        event = {"user_id": "user-1", "event_name": "purchase"}
        process_conversion(event)
        mock_clickhouse.insert.assert_not_called()


class TestRetrySemantics:
    def _event(self, event_id="evt-900"):
        return {"event_id": event_id, "user_id": "u1", "experiment_id": "e", "variant_key": "control",
                "timestamp": "2026-08-18T14:32:11+00:00"}

    def test_failed_insert_releases_dedup_and_raises(self, fake_redis, mock_clickhouse):
        import pytest

        from apps.events.clickhouse import EventStoreError

        mock_clickhouse.insert.side_effect = RuntimeError("clickhouse down")
        with pytest.raises(EventStoreError):
            process_exposure(self._event())
        assert not fake_redis.exists("dedup:evt-900")

        mock_clickhouse.insert.side_effect = None
        process_exposure(self._event())  # retry is not treated as a duplicate
        assert mock_clickhouse.insert.call_count == 2

    def test_clickhouse_unavailable_raises(self, fake_redis):
        from unittest.mock import patch

        import pytest

        from apps.events.clickhouse import EventStoreError

        with patch("apps.events.clickhouse.get_clickhouse_client", return_value=None):
            with pytest.raises(EventStoreError):
                process_conversion({"event_id": "c-1", "user_id": "u1"})


class TestHandleMessage:
    def _msg(self, topic, value, offset=7):
        from unittest.mock import MagicMock

        msg = MagicMock()
        msg.topic.return_value = topic
        msg.value.return_value = value
        msg.partition.return_value = 0
        msg.offset.return_value = offset
        return msg

    def test_commits_after_success(self, fake_redis, mock_clickhouse):
        import json
        from unittest.mock import MagicMock

        from apps.events.consumer import handle_message
        from apps.events.producer import TOPIC_EXPOSURES

        consumer = MagicMock()
        msg = self._msg(TOPIC_EXPOSURES, json.dumps({"event_id": "e-1", "user_id": "u"}).encode())
        assert handle_message(consumer, msg) is True
        consumer.commit.assert_called_once_with(message=msg, asynchronous=True)
        consumer.seek.assert_not_called()

    def test_rewinds_on_failure(self, fake_redis, mock_clickhouse):
        import json
        from unittest.mock import MagicMock

        from apps.events.consumer import handle_message
        from apps.events.producer import TOPIC_CONVERSIONS

        mock_clickhouse.insert.side_effect = RuntimeError("down")
        consumer = MagicMock()
        msg = self._msg(TOPIC_CONVERSIONS, json.dumps({"event_id": "c-9", "user_id": "u"}).encode(), offset=42)
        assert handle_message(consumer, msg) is False
        consumer.commit.assert_not_called()
        partition = consumer.seek.call_args.args[0]
        assert (partition.topic, partition.partition, partition.offset) == (TOPIC_CONVERSIONS, 0, 42)

    def test_poison_message_is_skipped(self, fake_redis, mock_clickhouse):
        from unittest.mock import MagicMock

        from apps.events.consumer import handle_message
        from apps.events.producer import TOPIC_EXPOSURES

        consumer = MagicMock()
        msg = self._msg(TOPIC_EXPOSURES, b"\xff not json")
        assert handle_message(consumer, msg) is True
        consumer.commit.assert_called_once()
        mock_clickhouse.insert.assert_not_called()
