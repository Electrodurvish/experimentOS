import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest
from experimentos_sdk import ExperimentOSClient, ExperimentOSError


class _Handler(BaseHTTPRequestHandler):
    calls = []
    fail = False

    def do_POST(self):  # noqa: N802 (http.server API)
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        type(self).calls.append((self.path, self.headers.get("X-API-Key"), body))
        if type(self).fail:
            self.send_response(503)
            self.end_headers()
            return
        if self.path == "/api/v1/evaluate/":
            response = {"evaluations": {
                key: {"assigned": key != "off_exp", "variant_key": None if key == "off_exp" else "treatment",
                      "version_number": 4, "reason": "assigned", "variant_payload": {"color": "blue"}}
                for key in body["experiment_keys"]
            }}
        else:
            response = {"status": "accepted"}
        data = json.dumps(response).encode()
        self.send_response(200)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args):
        pass


@pytest.fixture
def server():
    _Handler.calls = []
    _Handler.fail = False
    httpd = HTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{httpd.server_port}"
    httpd.shutdown()


def test_evaluate_matches_plan_shape(server):
    client = ExperimentOSClient(server, api_key="xos_test_abc")
    result = client.evaluate("checkout_v3", user_id="123", attributes={"country": "IN", "platform": "android"})
    assert result.to_dict() == {"variant": "treatment", "experiment": "checkout_v3", "version": 4}
    path, key, body = _Handler.calls[0]
    assert key == "xos_test_abc"
    assert body == {"user_id": "123", "experiment_keys": ["checkout_v3"],
                    "context": {"country": "IN", "platform": "android"}}


def test_evaluations_are_cached(server):
    client = ExperimentOSClient(server, api_key="k")
    client.evaluate("a", "u1")
    client.evaluate("a", "u1")
    client.evaluate("a", "u1", {"country": "US"})
    assert len(_Handler.calls) == 2


def test_get_feature(server):
    client = ExperimentOSClient(server, api_key="k")
    assert client.get_feature("new_checkout", "123") is True
    assert client.get_feature("off_exp", "123") is False


def test_failures_fall_back_to_unassigned(server):
    _Handler.fail = True
    client = ExperimentOSClient(server, api_key="k")
    result = client.evaluate("a", "u1")
    assert result.assigned is False and result.reason == "sdk_error"
    assert client.get_feature("a", "u1", default=True) is True
    assert client.track("purchase", "u1") is None


def test_unreachable_server():
    client = ExperimentOSClient("http://127.0.0.1:9", api_key="k", timeout=0.5)
    assert client.evaluate("a", "u1").reason == "sdk_error"


def test_track_raises_when_configured(server):
    _Handler.fail = True
    client = ExperimentOSClient(server, api_key="k", raise_on_error=True)
    with pytest.raises(ExperimentOSError) as exc:
        client.track("purchase", "u1")
    assert exc.value.status == 503


def test_track_and_telemetry_payloads(server):
    client = ExperimentOSClient(server, api_key="k")
    client.track("purchase", "u1", value=49.0, event_id="evt-1")
    client.send_telemetry("exp-uuid", "treatment", "latency_ms", 120)
    (p1, _, b1), (p2, _, b2) = _Handler.calls
    assert p1 == "/api/v1/events/track/" and b1["event_id"] == "evt-1" and b1["value"] == 49.0
    assert p2 == "/api/v1/observability/telemetry/" and b2["metric_value"] == 120.0
