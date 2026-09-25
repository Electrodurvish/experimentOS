#!/usr/bin/env bash
# Scenario: PostgreSQL goes down under evaluate load.
#
# Expected (from code):
#   - /healthz stays 200 (no dependency checks, apps/common/health.py:7-9) so
#     Kubernetes does NOT restart api pods for a DB outage (correct).
#   - /readyz returns 503 (apps/common/health.py:12-19) so pods leave the
#     Service endpoints.
#   - /evaluate fails: API-key authentication queries PostgreSQL and UPDATEs
#     last_used_at on every request (apps/accounts/authentication.py:18-31)
#     before the Redis config cache is consulted. There is no degraded mode.
#   - After recovery, Django reconnects (CONN_HEALTH_CHECKS=True in production
#     settings); requests succeed again without restarting the api.
# shellcheck source=lib.sh disable=SC2015
source "$(dirname "$0")/lib.sh"

OUTAGE="${OUTAGE:-20}"
health() { http_code "$BASE_URL/healthz"; }
ready()  { http_code "$BASE_URL/readyz"; }

ensure_seed
load_start postgres
sleep 3
service_stop db
t_down="$(date +%s)"
sleep 5

c="$(health)"; [ "$c" = "200" ] && pass "/healthz 200 with DB down (no restart loop)" || fail "/healthz $c with DB down"
c="$(ready)";  [ "$c" = "503" ] && pass "/readyz 503 with DB down (pod removed from endpoints)" || fail "/readyz $c with DB down (expected 503)"
c="$(evaluate_code during)"
if [ "$c" = "200" ]; then info "evaluate 200 with DB down (unexpected: auth needs DB)"; else pass "evaluate fails with $c while DB is down (expected: no degraded mode)"; fi

sleep "$OUTAGE"
service_start db
wait_healthy db 90 || fail "db did not become healthy"
t_up="$(date +%s)"

rec="$(wait_for_code 200 60 ready || true)"
[ "$rec" != "-1" ] && pass "/readyz back to 200 ${rec}s after DB healthy" || fail "/readyz not 200 within 60s"
rec="$(wait_for_code 200 60 evaluate_code after || true)"
[ "$rec" != "-1" ] && pass "evaluate recovered ${rec}s after DB healthy, without api restart" || fail "evaluate did not recover within 60s"
sleep 3
load_stop

load_summary
info "outage window ${t_down}..${t_up}: non-200 = $(awk -v a="$t_down" -v b="$t_up" '$1>=a && $1<b && $2!="200"' "$LOAD_FILE" | wc -l | tr -d ' ')"
info "first 200 after DB up: $(awk -v b="$t_up" '$1>=b && $2=="200" {print $1 - b "s"; exit}' "$LOAD_FILE")"

finish
