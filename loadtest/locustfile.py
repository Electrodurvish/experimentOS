"""
Locust alternative to the k6 scripts (same endpoints, same seed file).

    pip install locust
    python loadtest/seed.py --base-url http://localhost:8000 --out loadtest/seed.json
    locust -f loadtest/locustfile.py --host http://localhost:8000            # web UI on :8089
    locust -f loadtest/locustfile.py --host http://localhost:8000 \
        --headless -u 200 -r 50 -t 2m --csv loadtest/results/locust

Locust is closed-model (N users looping with wait_time) rather than k6's
open-model constant arrival rate, so "users" is not RPS. Use a constant
throughput wait time to approximate a target rate:
    LOCUST_RPS_PER_USER=5 -u 200  ->  ~1000 req/s if the server keeps up.
For the RPS ladder in docs/load-testing.md prefer k6; a single Python locust
worker saturates well below 5K RPS (use --processes or distributed workers).

Env: SEED_FILE (default loadtest/seed.json), API_KEY, EXPERIMENT_KEYS,
     USER_POOL, TRACK_WEIGHT / EVALUATE_WEIGHT, LOCUST_RPS_PER_USER.
"""

import json
import os
import random
import uuid
from pathlib import Path

from locust import FastHttpUser, between, constant_throughput, events, task

HERE = Path(__file__).resolve().parent


def _load_config():
    seed_path = Path(os.environ.get("SEED_FILE", HERE / "seed.json"))
    seed = {}
    if seed_path.exists():
        seed = json.loads(seed_path.read_text())
    api_key = os.environ.get("API_KEY", seed.get("api_key", ""))
    keys_env = os.environ.get("EXPERIMENT_KEYS")
    keys = [k.strip() for k in keys_env.split(",")] if keys_env else seed.get("experiment_keys", [])
    return api_key, [k for k in keys if k]


API_KEY, EXPERIMENT_KEYS = _load_config()
USER_POOL = int(os.environ.get("USER_POOL", "100000"))
RPS_PER_USER = float(os.environ.get("LOCUST_RPS_PER_USER", "0"))
EVENT_NAMES = ["purchase", "signup", "add_to_cart", "page_view"]


@events.test_start.add_listener
def _check_config(environment, **kwargs):
    if not API_KEY or not EXPERIMENT_KEYS:
        raise RuntimeError("Missing API key / experiment keys: run loadtest/seed.py or set API_KEY + EXPERIMENT_KEYS")


class SDKUser(FastHttpUser):
    """Simulates an SDK: evaluates experiments and tracks conversion events."""

    wait_time = constant_throughput(RPS_PER_USER) if RPS_PER_USER > 0 else between(0.05, 0.2)

    def on_start(self):
        self.headers = {"X-API-Key": API_KEY, "Content-Type": "application/json"}

    def _user_id(self):
        return f"user-{random.randrange(USER_POOL)}"

    @task(int(os.environ.get("EVALUATE_WEIGHT", "4")))
    def evaluate(self):
        body = {
            "user_id": self._user_id(),
            "experiment_keys": EXPERIMENT_KEYS,
            "context": {"country": "US", "platform": "web"},
        }
        with self.client.post(
            "/api/v1/evaluate/", json=body, headers=self.headers, name="evaluate", catch_response=True
        ) as resp:
            if resp.status_code != 200:
                resp.failure(f"HTTP {resp.status_code}")
                return
            try:
                evaluations = resp.json()["evaluations"]
            except (ValueError, KeyError):
                resp.failure("malformed response")
                return
            if not all(v.get("assigned") for v in evaluations.values()):
                resp.failure("not all experiments assigned")

    @task(int(os.environ.get("TRACK_WEIGHT", "1")))
    def track(self):
        body = {
            "event_id": str(uuid.uuid4()),
            "user_id": self._user_id(),
            "event_name": random.choice(EVENT_NAMES),
            "value": round(random.random() * 100, 2),
        }
        with self.client.post(
            "/api/v1/events/track/", json=body, headers=self.headers, name="track", catch_response=True
        ) as resp:
            if resp.status_code != 202:
                resp.failure(f"HTTP {resp.status_code}")
