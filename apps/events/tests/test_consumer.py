from unittest.mock import patch

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
