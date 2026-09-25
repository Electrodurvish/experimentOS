#!/usr/bin/env bash
# Scenario: Redis goes down under evaluate load.
#
# Designed behaviour (from code):
#   - Experiment config cache reads/writes swallow redis.RedisError and fall
#     back to PostgreSQL (apps/engine/cache.py:40-65).
#   - Distributed locks fail closed: acquisition error -> LockAcquisitionError
#     (apps/engine/locks.py:48-63) -> state transitions / version creation
#     return 409 (apps/experiments/views.py:116-120).
#   - Consumer dedup fails open: events are processed without dedup
#     (apps/events/consumer.py:28-30), so duplicates can reach ClickHouse.
#   - DRF throttles (APIKeyRateThrottle, AuthRateThrottle, UserRateThrottle)
#     read/write the Redis-backed Django cache (config/settings/base.py CACHES)
#     with no exception handling. In a local run this made /evaluate return 500
#     while Redis was down - i.e. the cache fallback above is currently
#     unreachable for throttled endpoints. This script reports what it sees.
# shellcheck source=lib.sh disable=SC2015
source "$(dirname "$0")/lib.sh"

OUTAGE="${OUTAGE:-20}"

ensure_seed
TOKEN="$(jwt_token)"

log "baseline"
code="$(evaluate_code base)"; [ "$code" = "200" ] && pass "evaluate 200 before outage" || fail "evaluate $code before outage"

load_start redis
sleep 3
service_stop redis
t_down="$(date +%s)"
sleep "$OUTAGE"

code="$(evaluate_code during)"
if [ "$code" = "200" ]; then
  pass "evaluate still answers 200 with Redis down (cache miss -> PostgreSQL)"
else
  fail "evaluate returned $code with Redis down (expected 200 by cache design; see throttling note)"
fi

exp_id="$(curl -s "$BASE_URL/api/v1/experiments/?search=$EXPERIMENT_KEY" -H "Authorization: Bearer $TOKEN" \
  | python3 -c 'import json,sys
try: print(json.load(sys.stdin)["results"][0]["id"])
except Exception: print("")')"
if [ -n "$exp_id" ]; then
  code="$(http_code -X POST "$BASE_URL/api/v1/experiments/$exp_id/pause/" -H "Authorization: Bearer $TOKEN")"
  if [ "$code" = "409" ]; then pass "state transition refused with 409 (lock fails closed)"; else info "pause returned $code (409 expected by lock design)"; fi
else
  info "could not list experiments during outage (dashboard API unavailable) - transition not attempted"
fi

service_start redis
wait_healthy redis 60 || fail "redis did not become healthy"
t_up="$(date +%s)"
rec="$(wait_for_code 200 60 evaluate_code after || true)"
[ "$rec" != "-1" ] && pass "evaluate recovered ${rec}s after Redis came back" || fail "evaluate did not recover within 60s"
sleep 3
load_stop

load_summary
info "during outage window: 200=$(awk -v a="$t_down" -v b="$t_up" '$1>=a && $1<b && $2=="200"' "$LOAD_FILE" | wc -l | tr -d ' ') non-200=$(awk -v a="$t_down" -v b="$t_up" '$1>=a && $1<b && $2!="200"' "$LOAD_FILE" | wc -l | tr -d ' ')"

# Leave the experiment running for the next scenarios if the pause went through.
if [ -n "${exp_id:-}" ]; then
  http_code -X POST "$BASE_URL/api/v1/experiments/$exp_id/start/" -H "Authorization: Bearer $TOKEN" >/dev/null
fi

finish
