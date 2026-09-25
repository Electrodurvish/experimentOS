# ExperimentOS Python SDK

Standard-library-only client for the ExperimentOS evaluation and event APIs.

```python
from experimentos_sdk import ExperimentOSClient

client = ExperimentOSClient("https://experimentos.example.com", api_key="xos_live_...")

client.evaluate("checkout_v3", user_id="123", attributes={"country": "IN", "platform": "android"}).to_dict()
# {"variant": "treatment", "experiment": "checkout_v3", "version": 4}

if client.get_feature("new_checkout", user_id="123"):
    ...

client.track("purchase", user_id="123", value=49.0)                      # conversion event
client.send_telemetry(experiment_id, "treatment", "latency_ms", 182.0)    # production telemetry
```

Behavior:

- `evaluate()` / `get_feature()` never raise. On network or server errors the user gets the
  unassigned (control) experience with `reason="sdk_error"`.
- Evaluations are cached for `cache_ttl` seconds (default 60) per experiment, user and attributes.
  Assignment is deterministic and sticky server-side, so this is safe.
- `track()` sends an `event_id` (random by default); pass your own to make retries idempotent —
  the event consumer deduplicates by `event_id`.

Run the tests: `cd sdk/python && python -m pytest`.
