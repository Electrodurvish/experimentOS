#!/usr/bin/env python3
"""
Populate a running ExperimentOS with a demo story, using only the public REST API.

    python3 scripts/demo_data.py --base-url http://localhost:8000

Creates an organization "Acme" with project "Web store" and:

- checkout_v3      +conversion but worse latency/error rate; the error-rate guardrail
                   breaches and the decision engine rolls it back 50% -> 10%
- new_onboarding   healthy winner at 25% rollout
- pricing_page     no measurable effect
- search_ranking   draft, not started

then drives users through /evaluate and /events/track, pushes production telemetry,
waits for the event pipeline, and prints the login. Standard library only.
"""

import argparse
import json
import random
import sys
import time
import urllib.error
import urllib.request
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

EMAIL = "demo@experimentos.local"
PASSWORD = "ExperimentOS-demo-1"

EXPERIMENTS = [
    # key, name, hypothesis, control rate, treatment rate, start
    ("checkout_v3", "Checkout v3", "A one-page checkout increases purchase conversion.", 0.10, 0.125, True),
    ("new_onboarding", "New onboarding", "A guided onboarding increases sign-up completion.", 0.20, 0.235, True),
    ("pricing_page", "Pricing page layout", "A comparison table increases upgrades.", 0.08, 0.08, True),
    ("search_ranking", "Search ranking v2", "Personalized ranking increases add-to-cart.", 0.0, 0.0, False),
]


class Api:
    def __init__(self, base):
        self.base = base.rstrip("/")
        self.token = None
        self.api_key = None

    def call(self, method, path, body=None, sdk=False, ok=(200, 201, 202, 204)):
        headers = {"Content-Type": "application/json"}
        if sdk:
            headers["X-API-Key"] = self.api_key
        elif self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        data = json.dumps(body).encode() if body is not None else None
        request = urllib.request.Request(self.base + path, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                raw = response.read()
                return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as exc:
            if exc.code in ok:
                return {}
            raise RuntimeError(f"{method} {path} -> {exc.code}: {exc.read()[:300]!r}") from None


def log(msg):
    print(f"[demo] {msg}", flush=True)


def wait_for_api(api, seconds=300):
    deadline = time.time() + seconds
    while time.time() < deadline:
        try:
            if api.call("GET", "/readyz").get("status") == "ok":
                return
        except Exception:
            pass
        time.sleep(3)
    sys.exit("API did not become ready; check `docker compose logs api`.")


def login(api):
    try:
        api.call("POST", "/api/v1/auth/register/", {"email": EMAIL, "username": "demo", "password": PASSWORD})
    except RuntimeError:
        pass  # already registered
    api.token = api.call("POST", "/api/v1/auth/token/", {"email": EMAIL, "password": PASSWORD})["access"]


def variants():
    return [
        {"key": "control", "name": "Control", "is_control": True, "traffic_percentage": 5000,
         "bucket_start": 0, "bucket_end": 4999, "payload": {"variant": "control"}},
        {"key": "treatment", "name": "Treatment", "is_control": False, "traffic_percentage": 5000,
         "bucket_start": 5000, "bucket_end": 9999, "payload": {"variant": "treatment"}},
    ]


def setup(api):
    orgs = api.call("GET", "/api/v1/organizations/?page_size=100")["results"]
    org = next((o for o in orgs if o["name"] == "Acme"), None) or api.call(
        "POST", "/api/v1/organizations/", {"name": "Acme"})
    projects = api.call("GET", f"/api/v1/projects/?organization={org['id']}&page_size=100")["results"]
    project = next((p for p in projects if p["name"] == "Web store"), None) or api.call(
        "POST", "/api/v1/projects/", {"name": "Web store", "organization_id": org["id"]})
    api.api_key = api.call("POST", "/api/v1/auth/api-keys/",
                           {"name": f"demo-{uuid.uuid4().hex[:6]}", "project_id": project["id"]})["key"]

    listing = api.call("GET", f"/api/v1/experiments/?project={project['id']}&page_size=100")["results"]
    existing = {e["key"]: e for e in listing}
    if "checkout_v3" in existing:
        return project, existing, False

    created = {}
    for key, name, hypothesis, _, _, start in EXPERIMENTS:
        exp = api.call("POST", "/api/v1/experiments/", {
            "project_id": project["id"], "key": key, "name": name, "hypothesis": hypothesis,
        })
        api.call("POST", f"/api/v1/experiments/{exp['id']}/versions/", {
            "traffic_allocation": 10000, "variants": variants(),
            "targeting": {"rules_json": {"operator": "AND", "conditions": [
                {"field": "country", "operator": "in", "value": ["IN", "US", "GB", "DE"]},
            ]}},
        })
        api.call("POST", f"/api/v1/experiments/{exp['id']}/metrics/", {
            "name": "Purchase conversion", "event_name": f"{key}_convert", "metric_type": "PRIMARY"})
        api.call("POST", f"/api/v1/experiments/{exp['id']}/metrics/", {
            "name": "Revenue per user", "event_name": f"{key}_convert", "metric_type": "SECONDARY",
            "aggregation": "MEAN_VALUE"})
        if start:
            for status in ("REVIEW", "APPROVED"):
                api.call("POST", f"/api/v1/experiments/{exp['id']}/transition/", {"status": status})
            api.call("POST", f"/api/v1/experiments/{exp['id']}/start/")
        created[key] = api.call("GET", f"/api/v1/experiments/{exp['id']}/")
        log(f"experiment {key} {'RUNNING' if start else 'DRAFT'}")

    checkout = created["checkout_v3"]["id"]
    api.call("PUT", f"/api/v1/experiments/{checkout}/rollout-policy/", {
        "stages": [1000, 2500, 5000, 10000], "rollback_percentage": 1000, "auto_rollback": True})
    for guardrail in (
        {"name": "Error rate", "metric_name": "error_rate", "operator": "RELATIVE_INCREASE_GT", "threshold": 50},
        {"name": "Checkout latency", "metric_name": "latency_ms", "operator": "RELATIVE_INCREASE_GT",
         "threshold": 30, "action": "PAUSE"},
    ):
        api.call("POST", f"/api/v1/experiments/{checkout}/guardrails/", guardrail)
    for pct in (1000, 2500, 5000):
        api.call("POST", f"/api/v1/experiments/{checkout}/rollout/", {"percentage": pct, "reason": "Staged rollout"})
    api.call("POST", f"/api/v1/experiments/{created['new_onboarding']['id']}/rollout/",
             {"percentage": 2500, "reason": "Initial ramp"})
    return project, created, True


def traffic(api, experiments, users):
    rates = {key: (c, t) for key, _, _, c, t, start in EXPERIMENTS if start}
    keys = list(rates)
    countries = ["IN", "US", "GB", "DE", "BR"]
    platforms = ["android", "ios", "web"]
    counts = {"evaluated": 0, "conversions": 0}

    def one(i):
        user = f"demo-user-{i}"
        context = {"country": countries[i % 5], "platform": platforms[i % 3]}
        result = api.call("POST", "/api/v1/evaluate/", {"user_id": user, "experiment_keys": keys, "context": context},
                          sdk=True)["evaluations"]
        conversions = 0
        for key, ev in result.items():
            if not ev["assigned"]:
                continue
            control, treatment = rates[key]
            p = treatment if ev["variant_key"] == "treatment" else control
            local = random.Random(f"{user}:{key}")
            if local.random() < p:
                api.call("POST", "/api/v1/events/track/", {
                    "user_id": user, "event_name": f"{key}_convert", "value": round(local.uniform(20, 120), 2),
                }, sdk=True)
                conversions += 1
        return conversions

    with ThreadPoolExecutor(max_workers=12) as pool:
        for n, conv in enumerate(pool.map(one, range(users)), 1):
            counts["evaluated"] += 1
            counts["conversions"] += conv
            if n % 2000 == 0:
                log(f"{n}/{users} users evaluated")
    return counts


def telemetry(api, experiments):
    """Two hours of per-variant production metrics; checkout_v3 treatment regresses, then spikes."""
    now = datetime.now(timezone.utc)
    points = []
    for key, exp in experiments.items():
        if exp["status"] != "RUNNING":
            continue
        bad = key == "checkout_v3"
        for step in range(24):
            at = (now - timedelta(minutes=5 * (23 - step))).isoformat()
            wiggle = 1 + 0.03 * ((step * 7) % 5 - 2)
            for variant in ("control", "treatment"):
                treat = variant == "treatment"
                latency = 120 * wiggle * (1.45 if bad and treat else 1.0)
                errors = 1.1 * wiggle * (3.2 if bad and treat else 1.0)
                if bad and treat and step == 23:
                    errors = 9.5  # the anomaly
                for name, value in (("latency_ms", latency), ("error_rate", errors)):
                    points.append({"experiment_id": exp["id"], "variant_key": variant, "metric_name": name,
                                   "metric_value": round(value, 3), "event_time": at})
    for i in range(0, len(points), 200):
        api.call("POST", "/api/v1/observability/telemetry/batch/", {"data_points": points[i:i + 200]}, sdk=True)
    log(f"sent {len(points)} telemetry points")


def wait_for_pipeline(api, experiments, expected_conversions):
    deadline = time.time() + 180
    total = 0
    while time.time() < deadline:
        total = 0
        for exp in experiments.values():
            if exp["status"] == "RUNNING":
                res = api.call("GET", f"/api/v1/experiments/{exp['id']}/results/")
                total += sum(v["conversions"] for v in res["variants"].values())
        # Allow a handful of events still in flight rather than waiting out the timeout.
        if total >= expected_conversions * 0.995:
            return
        log(f"waiting for events to reach ClickHouse ({total}/{expected_conversions})")
        time.sleep(5)
    log(f"continuing with {total}/{expected_conversions} conversions stored")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--users", type=int, default=8000)
    args = parser.parse_args()

    api = Api(args.base_url)
    log(f"waiting for {args.base_url}")
    wait_for_api(api)
    login(api)
    project, experiments, fresh = setup(api)
    if fresh:
        counts = traffic(api, experiments, args.users)
        log(f"{counts['evaluated']} users evaluated, {counts['conversions']} conversions tracked")
        telemetry(api, experiments)
        wait_for_pipeline(api, experiments, counts["conversions"])
        checkout = experiments["checkout_v3"]["id"]
        decision = api.call("POST", f"/api/v1/experiments/{checkout}/decision/", {"apply": True})
        log(f"checkout_v3 decision: {decision['recommendation']} ({decision['confidence_label']}) "
            f"applied={decision.get('applied')}")
    else:
        log("demo data already present; skipping traffic")

    print()
    print("  Dashboard:  http://localhost:8080")
    print(f"  Login:      {EMAIL} / {PASSWORD}")
    print("  API docs:   http://localhost:8000/api/docs/")
    print(f"  SDK key:    {api.api_key}")


if __name__ == "__main__":
    main()
