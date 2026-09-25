import time

import pytest


@pytest.mark.django_db
def test_beat_and_sweep_gauges_exposed(api_client, fake_redis):
    from apps.decisions.tasks import beat_heartbeat, evaluate_running_experiments

    beat_heartbeat()
    evaluate_running_experiments()
    body = api_client.get("/metrics").content.decode()
    beat = [line for line in body.splitlines() if line.startswith("celery_beat_last_heartbeat_timestamp_seconds ")]
    sweep = [line for line in body.splitlines() if line.startswith("decision_sweep_last_success_timestamp_seconds ")]
    assert beat and abs(float(beat[0].split()[1]) - time.time()) < 60
    assert sweep


def test_multiprocess_registry(tmp_path, monkeypatch):
    from prometheus_client import REGISTRY

    from apps.observability.metrics import metrics_registry

    assert metrics_registry() is REGISTRY
    monkeypatch.setenv("PROMETHEUS_MULTIPROC_DIR", str(tmp_path))
    assert metrics_registry() is not REGISTRY


def test_throttle_fails_open_when_cache_down(rf):
    from unittest.mock import patch

    from apps.common.throttling import FailOpenUserRateThrottle

    request = rf.get("/")
    request.user = type("U", (), {"is_authenticated": True, "pk": 1})()
    throttle = FailOpenUserRateThrottle()
    with patch.object(throttle, "cache") as cache:
        cache.get.side_effect = ConnectionError("redis down")
        assert throttle.allow_request(request, None) is True
