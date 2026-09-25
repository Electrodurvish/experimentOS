#!/usr/bin/env bash
# Scenario: the api process is killed (SIGKILL) under load.
#
# Expected:
#   - docker-compose: the api service has no restart policy, so it stays down
#     until started again; clients see connection errors (000) meanwhile.
#     This script measures error count and time-to-first-success after restart.
#   - Kubernetes (Helm chart): the Deployment controller replaces the pod, the
#     startup/readiness probes gate traffic, and with >=2 replicas + PDB the
#     Service keeps routing to the surviving pods. Use MODE=k8s to test that:
#       MODE=k8s NAMESPACE=experimentos BASE_URL=https://<host> scripts/chaos/kill-api.sh
#   - Events already handed to the producer's in-memory buffer but not yet
#     delivered are lost on SIGKILL: flush_producer() exists
#     (apps/events/producer.py:120-123) but nothing calls it on shutdown.
# shellcheck source=lib.sh disable=SC2015
source "$(dirname "$0")/lib.sh"

MODE="${MODE:-compose}"
NAMESPACE="${NAMESPACE:-experimentos}"
DOWN="${DOWN:-10}"

ensure_seed
load_start api
sleep 3
t_kill="$(date +%s)"

if [ "$MODE" = "k8s" ]; then
  pod="$(kubectl -n "$NAMESPACE" get pods -l app.kubernetes.io/component=api -o jsonpath='{.items[0].metadata.name}')"
  log "force-deleting pod $pod"
  kubectl -n "$NAMESPACE" delete pod "$pod" --grace-period=0 --force >/dev/null 2>&1
  sleep 20
  kubectl -n "$NAMESPACE" get pods -l app.kubernetes.io/component=api
  kubectl -n "$NAMESPACE" rollout status deploy -l app.kubernetes.io/component=api --timeout=120s \
    && pass "Deployment restored desired replicas" || fail "rollout did not complete"
  t_up="$(date +%s)"
else
  service_kill api
  sleep "$DOWN"
  service_start api
  t_up="$(date +%s)"
  rec="$(wait_for_code 200 90 evaluate_code after || true)"
  [ "$rec" != "-1" ] && pass "api serving again ${rec}s after start" || fail "api not serving within 90s"
fi

sleep 5
load_stop
load_summary
errors="$(awk -v a="$t_kill" '$1>=a && $2!="200"' "$LOAD_FILE" | wc -l | tr -d ' ')"
info "non-200 responses from kill onwards: $errors"
first_ok="$(awk -v b="$t_up" '$1>=b && $2=="200" {print $1 - b; exit}' "$LOAD_FILE")"
info "first 200 after restart/reschedule: ${first_ok:-none}s"
if [ "$MODE" = "k8s" ]; then
  [ "$errors" -eq 0 ] && pass "no client-visible errors (other replicas absorbed traffic)" \
    || info "$errors client-visible errors (expected ~0 with >=2 replicas; single replica will show errors)"
fi

finish
