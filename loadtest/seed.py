#!/usr/bin/env python3
"""
Seed an ExperimentOS instance for load / failure testing, using only the public
REST API (no Django imports, stdlib only), so it works against docker-compose,
a CI service stack or a remote cluster alike.

It creates: user -> JWT -> organization -> project -> N running A/B experiments
(50/50, control + treatment) -> SDK API key, and writes the result as JSON:

    {"base_url": ..., "api_key": "...", "project_id": "...",
     "experiment_keys": ["lt-exp-1", ...], "email": ..., "password": ...}

Usage:
    python loadtest/seed.py --base-url http://localhost:8000 --out loadtest/seed.json
    python loadtest/seed.py --experiments 5 --prefix checkout

Exit code is non-zero (with the failing response printed) on any API error.
"""

import argparse
import json
import secrets
import sys
import urllib.error
import urllib.request


class APIError(RuntimeError):
    pass


class Client:
    def __init__(self, base_url, host_header=None, timeout=30):
        self.base_url = base_url.rstrip("/")
        self.token = None
        self.host_header = host_header
        self.timeout = timeout

    def request(self, method, path, body=None, expected=(200, 201), auth=True):
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(self.base_url + path, data=data, method=method)
        req.add_header("Content-Type", "application/json")
        req.add_header("Accept", "application/json")
        if self.host_header:
            req.add_header("Host", self.host_header)
        if auth and self.token:
            req.add_header("Authorization", f"Bearer {self.token}")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                status, raw = resp.status, resp.read()
        except urllib.error.HTTPError as e:
            status, raw = e.code, e.read()
        except urllib.error.URLError as e:
            raise APIError(f"{method} {path}: cannot reach {self.base_url}: {e.reason}") from e

        text = raw.decode("utf-8", errors="replace")
        if status not in expected:
            raise APIError(f"{method} {path} -> HTTP {status}: {text[:1000]}")
        return json.loads(text) if text else {}


def variants_50_50():
    return [
        {
            "key": "control",
            "name": "Control",
            "is_control": True,
            "traffic_percentage": 5000,
            "bucket_start": 0,
            "bucket_end": 4999,
            "payload": {"variant": "control"},
        },
        {
            "key": "treatment",
            "name": "Treatment",
            "is_control": False,
            "traffic_percentage": 5000,
            "bucket_start": 5000,
            "bucket_end": 9999,
            "payload": {"variant": "treatment"},
        },
    ]


def seed(args):
    c = Client(args.base_url, host_header=args.host_header)
    run_id = secrets.token_hex(3)
    email = args.email or f"loadtest+{run_id}@example.com"
    password = args.password or f"Lt-{secrets.token_urlsafe(12)}"

    # 1. User (tolerate "already exists" when --email/--password are reused)
    try:
        c.request(
            "POST",
            "/api/v1/auth/register/",
            {"email": email, "username": email.split("@")[0], "password": password},
            expected=(201,),
            auth=False,
        )
        log(f"registered {email}")
    except APIError as e:
        if not args.email or "HTTP 400" not in str(e):
            raise
        log(f"user {email} already exists, logging in")

    # 2. JWT
    tokens = c.request("POST", "/api/v1/auth/token/", {"email": email, "password": password}, auth=False)
    c.token = tokens["access"]

    # 3. Organization + project
    org = c.request("POST", "/api/v1/organizations/", {"name": f"{args.prefix} org {run_id}"}, expected=(201,))
    project = c.request(
        "POST",
        "/api/v1/projects/",
        {"name": f"{args.prefix} project {run_id}", "organization_id": org["id"]},
        expected=(201,),
    )
    log(f"organization {org['id']}, project {project['id']}")

    # 4. Experiments: create -> version with variants -> DRAFT->REVIEW->APPROVED->RUNNING
    keys = []
    for i in range(1, args.experiments + 1):
        key = f"{args.prefix}-exp-{i}-{run_id}"
        exp = c.request(
            "POST",
            "/api/v1/experiments/",
            {
                "project_id": project["id"],
                "key": key,
                "name": f"Load test experiment {i}",
                "hypothesis": "Seeded for load/failure testing",
                "experiment_type": "AB",
            },
            expected=(201,),
        )
        c.request(
            "POST",
            f"/api/v1/experiments/{exp['id']}/versions/",
            {"traffic_allocation": 10000, "variants": variants_50_50()},
            expected=(201,),
        )
        for status in ("REVIEW", "APPROVED", "RUNNING"):
            c.request("POST", f"/api/v1/experiments/{exp['id']}/transition/", {"status": status})
        keys.append(key)
        log(f"experiment {key} RUNNING")

    # 5. SDK API key (returned once, in plaintext)
    api_key = c.request(
        "POST",
        "/api/v1/auth/api-keys/",
        {"name": f"loadtest-{run_id}", "project_id": project["id"], "environment": "test"},
        expected=(201,),
    )["key"]

    result = {
        "base_url": args.base_url,
        "api_key": api_key,
        "project_id": project["id"],
        "organization_id": org["id"],
        "experiment_keys": keys,
        "email": email,
        "password": password,
    }
    return result


def log(msg):
    print(f"[seed] {msg}", file=sys.stderr)


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--base-url", default="http://localhost:8000")
    p.add_argument("--host-header", default=None, help="Override Host header (e.g. behind a port-forward)")
    p.add_argument("--experiments", type=int, default=3)
    p.add_argument("--prefix", default="lt")
    p.add_argument("--email", default=None)
    p.add_argument("--password", default=None)
    p.add_argument("--out", default="-", help="Output JSON path, '-' for stdout")
    args = p.parse_args()

    try:
        result = seed(args)
    except APIError as e:
        print(f"[seed] FAILED: {e}", file=sys.stderr)
        return 1

    payload = json.dumps(result, indent=2)
    if args.out == "-":
        print(payload)
    else:
        with open(args.out, "w") as f:
            f.write(payload + "\n")
        log(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
