"""
End-to-end flow against a real ClickHouse (plan §45):

    create experiment → start → evaluate users (SDK API key) → exposure events
    → conversion events → consumer (with duplicate deliveries) → ClickHouse
    → results → health → decision

Kafka itself is replaced by capturing what the producer would publish and handing
those messages to the consumer's processing functions, so the test exercises the
real serialization, deduplication and ClickHouse queries.

Skipped unless E2E_CLICKHOUSE_HOST is set, e.g.:
    docker run -d -p 18123:8123 clickhouse/clickhouse-server:24.3
    E2E_CLICKHOUSE_HOST=localhost E2E_CLICKHOUSE_PORT=18123 poetry run pytest apps/common/tests/test_e2e.py
"""

import json
import os
import uuid
from unittest.mock import patch

import pytest
from rest_framework.test import APIClient

from apps.engine.hasher import compute_bucket

pytestmark = [
    pytest.mark.django_db,
    pytest.mark.skipif(not os.environ.get("E2E_CLICKHOUSE_HOST"), reason="E2E_CLICKHOUSE_HOST not set"),
]


@pytest.fixture
def clickhouse():
    import clickhouse_connect

    host = os.environ["E2E_CLICKHOUSE_HOST"]
    port = int(os.environ.get("E2E_CLICKHOUSE_PORT", "8123"))
    database = f"xos_e2e_{uuid.uuid4().hex[:8]}"
    admin = clickhouse_connect.get_client(host=host, port=port)
    admin.command(f"CREATE DATABASE {database}")
    client = clickhouse_connect.get_client(host=host, port=port, database=database)
    with patch("apps.events.clickhouse.get_clickhouse_client", return_value=client), \
            patch("apps.observability.telemetry.get_clickhouse_client", return_value=client):
        from apps.events.clickhouse import ensure_schema
        from apps.observability.telemetry import ensure_telemetry_schema

        ensure_schema()
        ensure_telemetry_schema()
        yield client
    admin.command(f"DROP DATABASE {database}")


def _published(mock_kafka, topic):
    return [json.loads(c.kwargs["value"]) for c in mock_kafka.produce.call_args_list if c.kwargs["topic"] == topic]


def test_full_experiment_flow(clickhouse, authenticated_client, project, api_key, mock_kafka, mock_cassandra,
                              settings):
    from apps.events import consumer, producer

    settings.KAFKA_ENABLED = True
    client = authenticated_client

    # 1. Create and configure the experiment
    response = client.post("/api/v1/experiments/", {
        "project_id": str(project.id), "key": "checkout_v3", "name": "Checkout v3",
    }, format="json")
    assert response.status_code == 201, response.data
    exp_id = response.data["id"]
    response = client.post(f"/api/v1/experiments/{exp_id}/versions/", {
        "traffic_allocation": 10000,
        "variants": [
            {"key": "control", "name": "Control", "is_control": True, "traffic_percentage": 5000,
             "bucket_start": 0, "bucket_end": 4999},
            {"key": "treatment", "name": "Treatment", "traffic_percentage": 5000,
             "bucket_start": 5000, "bucket_end": 9999},
        ],
    }, format="json")
    assert response.status_code == 201, response.data

    # 2. Walk the lifecycle to RUNNING
    for status_ in ("REVIEW", "APPROVED"):
        assert client.post(f"/api/v1/experiments/{exp_id}/transition/", {"status": status_},
                           format="json").status_code == 200
    assert client.post(f"/api/v1/experiments/{exp_id}/start/").data["status"] == "RUNNING"

    # 3. Evaluate users through the SDK endpoint
    sdk = APIClient()
    sdk.credentials(HTTP_X_API_KEY=api_key[1])
    users = [f"user-{i}" for i in range(2000)]
    assigned = {}
    for user in users:
        body = sdk.post("/api/v1/evaluate/", {"user_id": user, "experiment_keys": ["checkout_v3"]},
                        format="json").data
        evaluation = body["evaluations"]["checkout_v3"]
        assert evaluation["assigned"]
        assert evaluation["variant_key"] == ("control" if compute_bucket(user, "checkout_v3", 2) < 5000
                                             else "treatment")
        assigned[user] = evaluation["variant_key"]

    # 4. Conversions: treatment converts at 30%, control at 20% (deterministic by user index)
    for i, user in enumerate(users):
        rate = 30 if assigned[user] == "treatment" else 20
        if i % 100 < rate:
            assert sdk.post("/api/v1/events/track/", {"user_id": user, "event_name": "purchase", "value": 10},
                            format="json").status_code == 202

    exposures = _published(mock_kafka, producer.TOPIC_EXPOSURES)
    conversions = _published(mock_kafka, producer.TOPIC_CONVERSIONS)
    assert len(exposures) == len(users)

    # 5. Consumer processing, with every message delivered twice (at-least-once)
    for event in exposures + exposures:
        consumer.process_exposure(event)
    for event in conversions + conversions:
        consumer.process_conversion(event)
    assert clickhouse.query("SELECT count() FROM experiment_exposures").result_rows[0][0] == len(users)
    assert clickhouse.query("SELECT count() FROM conversion_events").result_rows[0][0] == len(conversions)

    # 6. Results from ClickHouse
    results = client.get(f"/api/v1/experiments/{exp_id}/results/").data
    control, treatment = results["variants"]["control"], results["variants"]["treatment"]
    assert control["unique_users"] + treatment["unique_users"] == len(users)
    assert treatment["conversion_rate"] > control["conversion_rate"]
    assert treatment["is_significant"] is True
    assert results["srm"]["is_mismatch"] is False

    # 7. Health and decision
    health = client.get(f"/api/v1/experiments/{exp_id}/health/").data["health"]
    assert health["dimensions"]["sample_ratio"]["score"] == 100
    decision = client.get(f"/api/v1/experiments/{exp_id}/decision/").data
    assert decision["recommendation"] in {"CONTINUE", "COMPLETE"}
    assert any(e["kind"] == "primary_metric" for e in decision["evidence"])

    # 8. Guardrail breach from production telemetry triggers a rollback
    client.post(f"/api/v1/experiments/{exp_id}/rollout/", {"percentage": 5000, "reason": "ramp"}, format="json")
    client.post(f"/api/v1/experiments/{exp_id}/guardrails/", {
        "name": "Error rate", "metric_name": "error_rate", "operator": "RELATIVE_INCREASE_GT", "threshold": 20,
    }, format="json")
    points = [{"experiment_id": exp_id, "variant_key": v, "metric_name": "error_rate", "metric_value": value}
              for v, value in (("control", 1.0), ("treatment", 4.0)) for _ in range(20)]
    assert sdk.post("/api/v1/observability/telemetry/batch/", {"data_points": points},
                    format="json").status_code == 202
    response = client.post(f"/api/v1/experiments/{exp_id}/decision/", {"apply": True}, format="json")
    assert response.data["recommendation"] == "ROLLBACK"
    assert response.data["applied"] == {"action": "rollback", "from": 5000, "to": 1000}

    timeline = [e["event_type"] for e in client.get(f"/api/v1/experiments/{exp_id}/timeline/").data["timeline"]]
    assert timeline[:3] == ["experiment_created", "version_created", "experiment_started"]
    assert "rollback_triggered" in timeline
