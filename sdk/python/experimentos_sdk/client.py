"""
ExperimentOS Python SDK.

    client = ExperimentOSClient("https://experimentos.example.com", api_key="xos_live_...")

    client.evaluate("checkout_v3", user_id="123", attributes={"country": "IN", "platform": "android"})
    # Evaluation(experiment="checkout_v3", variant="treatment", version=4, assigned=True, ...)

    if client.get_feature("new_checkout", user_id="123"):
        ...

    client.track("purchase", user_id="123", value=49.0)

Design choices:
- Standard library only (urllib), so it drops into any service.
- Evaluations are cached per (experiment, user, attributes) for `cache_ttl` seconds;
  assignment is deterministic and sticky server-side, so caching is safe and keeps
  the hot path off the network.
- Failures never raise from evaluate()/get_feature(): the caller gets the control
  experience (assigned=False, reason="sdk_error") and the error is logged. track()
  and send_telemetry() raise ExperimentOSError only when raise_on_error=True.
"""

import json
import logging
import threading
import time
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

logger = logging.getLogger("experimentos_sdk")

DEFAULT_TIMEOUT = 2.0


class ExperimentOSError(Exception):
    def __init__(self, message, status=None):
        super().__init__(message)
        self.status = status


@dataclass(frozen=True)
class Evaluation:
    experiment: str
    variant: str | None
    version: int | None
    assigned: bool
    reason: str
    payload: dict = field(default_factory=dict)

    def to_dict(self):
        return {"variant": self.variant, "experiment": self.experiment, "version": self.version}


class ExperimentOSClient:
    def __init__(self, base_url, api_key, timeout=DEFAULT_TIMEOUT, cache_ttl=60.0, raise_on_error=False):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout
        self.cache_ttl = cache_ttl
        self.raise_on_error = raise_on_error
        self._cache = {}
        self._lock = threading.Lock()

    # ── Evaluation ──

    def evaluate(self, experiment, user_id, attributes=None):
        """Evaluate one experiment for a user. Never raises; falls back to unassigned."""
        return self.evaluate_many([experiment], user_id, attributes)[experiment]

    def evaluate_many(self, experiments, user_id, attributes=None):
        """Evaluate several experiments in one request. Returns {experiment_key: Evaluation}."""
        attributes = attributes or {}
        results, missing = {}, []
        now = time.monotonic()
        with self._lock:
            for key in experiments:
                cached = self._cache.get(self._cache_key(key, user_id, attributes))
                if cached and cached[0] > now:
                    results[key] = cached[1]
                else:
                    missing.append(key)

        if missing:
            try:
                body = self._post("/api/v1/evaluate/", {
                    "user_id": str(user_id),
                    "experiment_keys": missing,
                    "context": attributes,
                })
            except ExperimentOSError as exc:
                logger.warning("ExperimentOS evaluation failed: %s", exc)
                for key in missing:
                    results[key] = Evaluation(key, None, None, False, "sdk_error")
                return results

            expires = time.monotonic() + self.cache_ttl
            with self._lock:
                for key in missing:
                    data = body.get("evaluations", {}).get(key, {})
                    evaluation = Evaluation(
                        experiment=key,
                        variant=data.get("variant_key"),
                        version=data.get("version_number"),
                        assigned=bool(data.get("assigned")),
                        reason=data.get("reason", "unknown"),
                        payload=data.get("variant_payload") or {},
                    )
                    self._cache[self._cache_key(key, user_id, attributes)] = (expires, evaluation)
                    results[key] = evaluation
        return results

    def get_feature(self, feature, user_id, attributes=None, default=False):
        """
        Feature-flag view of an experiment: True when the user is assigned a
        non-control variant. The variant payload's "enabled" key overrides this.
        """
        evaluation = self.evaluate(feature, user_id, attributes)
        if not evaluation.assigned:
            return default
        if "enabled" in evaluation.payload:
            return bool(evaluation.payload["enabled"])
        return evaluation.variant not in (None, "control", "off")

    # ── Events ──

    def track(self, event_name, user_id, value=0.0, metadata=None, event_id=None, timestamp=None):
        """Track a conversion event. event_id makes retries idempotent (deduplicated server-side)."""
        payload = {
            "event_id": event_id or str(uuid.uuid4()),
            "user_id": str(user_id),
            "event_name": event_name,
            "value": value,
            "metadata": metadata or {},
            "timestamp": (timestamp or datetime.now(timezone.utc)).isoformat(),
        }
        return self._fire("/api/v1/events/track/", payload)

    def send_telemetry(self, experiment_id, variant, metric_name, value, event_time=None):
        """Report a production metric (latency_ms, error_rate, ...) for an experiment variant."""
        payload = {
            "experiment_id": str(experiment_id),
            "variant_key": variant,
            "metric_name": metric_name,
            "metric_value": float(value),
        }
        if event_time:
            payload["event_time"] = event_time.isoformat()
        return self._fire("/api/v1/observability/telemetry/", payload)

    def clear_cache(self):
        with self._lock:
            self._cache.clear()

    # ── HTTP ──

    def _fire(self, path, payload):
        try:
            return self._post(path, payload)
        except ExperimentOSError as exc:
            if self.raise_on_error:
                raise
            logger.warning("ExperimentOS request to %s failed: %s", path, exc)
            return None

    def _post(self, path, payload):
        request = urllib.request.Request(
            self.base_url + path,
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json", "X-API-Key": self.api_key},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                raw = response.read()
        except urllib.error.HTTPError as exc:
            raise ExperimentOSError(f"HTTP {exc.code}: {exc.read()[:200]!r}", status=exc.code) from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise ExperimentOSError(str(exc)) from exc
        return json.loads(raw) if raw else {}

    @staticmethod
    def _cache_key(experiment, user_id, attributes):
        return experiment, str(user_id), json.dumps(attributes, sort_keys=True, default=str)
