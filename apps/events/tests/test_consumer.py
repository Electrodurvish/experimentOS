
from apps.events.consumer import is_duplicate, mark_processed, process_conversion, process_exposure


class TestDeduplication:
    def test_new_event_is_not_duplicate(self, fake_redis):
        assert is_duplicate("evt-001") is False

    def test_marked_event_is_duplicate(self, fake_redis):
        assert is_duplicate("evt-002") is False
        mark_processed("evt-002")
        assert is_duplicate("evt-002") is True

    def test_check_does_not_mark(self, fake_redis):
        is_duplicate("evt-003")
        assert not fake_redis.exists("dedup:evt-003")

    def test_dedup_key_has_ttl(self, fake_redis):
        mark_processed("evt-005")
        assert 0 < fake_redis.ttl("dedup:evt-005") <= 86400


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

    def test_failed_insert_does_not_mark_and_raises(self, fake_redis, mock_clickhouse):
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


class TestFailureClassification:
    def _msg(self, topic, value, offset=3):
        from unittest.mock import MagicMock

        msg = MagicMock()
        msg.topic.return_value = topic
        msg.value.return_value = value
        msg.key.return_value = b"u"
        msg.partition.return_value = 0
        msg.offset.return_value = offset
        return msg

    def test_unavailable_retries_forever_without_dlq(self, fake_redis, mock_clickhouse):
        import json
        from unittest.mock import MagicMock, patch

        from clickhouse_connect.driver.exceptions import OperationalError

        from apps.events import consumer as c
        from apps.events.producer import TOPIC_EXPOSURES

        mock_clickhouse.insert.side_effect = OperationalError("connection refused")
        kafka = MagicMock()
        msg = self._msg(TOPIC_EXPOSURES, json.dumps({"event_id": "x1", "user_id": "u"}).encode())
        with patch.object(c, "_send_to_dlq") as dlq:
            results = [c.handle_message(kafka, msg) for _ in range(c.MAX_ATTEMPTS + 3)]
        assert results == [False] * (c.MAX_ATTEMPTS + 3)
        dlq.assert_not_called()
        kafka.commit.assert_not_called()

    def test_rejected_event_goes_to_dlq_after_budget(self, fake_redis, mock_clickhouse, mock_kafka):
        import json
        from unittest.mock import MagicMock

        from apps.events import consumer as c
        from apps.events.producer import TOPIC_CONVERSIONS

        c._attempts.clear()
        mock_clickhouse.insert.side_effect = ValueError("Cannot parse value")
        mock_kafka.produce.side_effect = lambda **kw: kw["callback"](None, None)
        kafka = MagicMock()
        msg = self._msg(TOPIC_CONVERSIONS, json.dumps({"event_id": "bad-1", "user_id": "u"}).encode(), offset=9)
        results = [c.handle_message(kafka, msg) for _ in range(c.MAX_ATTEMPTS)]
        assert results == [False] * (c.MAX_ATTEMPTS - 1) + [True]
        assert mock_kafka.produce.call_args.kwargs["topic"] == f"{TOPIC_CONVERSIONS}.dlq"
        kafka.commit.assert_called_once_with(message=msg, asynchronous=True)
        assert c._attempts == {}

    def test_dlq_failure_keeps_retrying(self, fake_redis, mock_clickhouse, mock_kafka):
        import json
        from unittest.mock import MagicMock

        from apps.events import consumer as c
        from apps.events.producer import TOPIC_CONVERSIONS

        c._attempts.clear()
        mock_clickhouse.insert.side_effect = ValueError("bad")
        mock_kafka.produce.side_effect = lambda **kw: kw["callback"]("broker down", None)
        kafka = MagicMock()
        msg = self._msg(TOPIC_CONVERSIONS, json.dumps({"event_id": "bad-2", "user_id": "u"}).encode(), offset=11)
        results = [c.handle_message(kafka, msg) for _ in range(c.MAX_ATTEMPTS)]
        assert results[-1] is False
        kafka.commit.assert_not_called()
        c._attempts.clear()


class TestHeartbeat:
    def test_healthcheck(self, tmp_path, settings):
        import pytest
        from django.core.management import call_command

        from apps.events.consumer import touch_heartbeat

        settings.CONSUMER_HEARTBEAT_FILE = str(tmp_path / "hb")
        with pytest.raises(SystemExit):
            call_command("consumer_healthcheck")
        touch_heartbeat()
        call_command("consumer_healthcheck", "--max-age", "5")
        with pytest.raises(SystemExit):
            call_command("consumer_healthcheck", "--max-age", "-1")
