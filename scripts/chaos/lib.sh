#!/usr/bin/env bash
# Shared helpers for the chaos scripts. Source it; don't run it.
#
# Assumes the docker-compose stack is up (docker compose up -d) with ClickHouse
# and Cassandra schemas created, and runs from anywhere inside the repo.
#
# Env overrides:
#   BASE_URL     api URL                (default http://localhost:8000)
#   SEED_FILE    output of seed.py      (default loadtest/seed.json; created if missing)
#   COMPOSE      compose command        (default "docker compose")
#   LOAD_WORKERS parallel curl loops    (default 4)

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
BASE_URL="${BASE_URL:-http://localhost:8000}"
SEED_FILE="${SEED_FILE:-$REPO_ROOT/loadtest/seed.json}"
LOAD_WORKERS="${LOAD_WORKERS:-4}"
read -r -a COMPOSE_CMD <<< "${COMPOSE:-docker compose}"
RESULTS_DIR="${RESULTS_DIR:-$REPO_ROOT/scripts/chaos/results}"
mkdir -p "$RESULTS_DIR"

RUN_ID="$(date +%s)-$$"
FAILURES=0

# ---------------------------------------------------------------- output

log()  { printf '\033[1;34m[chaos %s]\033[0m %s\n' "$(date +%H:%M:%S)" "$*"; }
pass() { printf '\033[1;32m  PASS\033[0m %s\n' "$*"; }
fail() { printf '\033[1;31m  FAIL\033[0m %s\n' "$*"; FAILURES=$((FAILURES + 1)); }
info() { printf '       %s\n' "$*"; }

finish() {
  if [ "$FAILURES" -eq 0 ]; then
    log "scenario finished: all expectations met"
  else
    log "scenario finished: $FAILURES expectation(s) not met (see FAIL lines)"
  fi
  return "$FAILURES"
}

# ---------------------------------------------------------------- compose

dc() { (cd "$REPO_ROOT" && "${COMPOSE_CMD[@]}" "$@"); }

service_stop()  { log "stopping $1"; dc stop "$1" >/dev/null; }
service_kill()  { log "SIGKILL $1"; dc kill -s SIGKILL "$1" >/dev/null; }
service_start() { log "starting $1"; dc start "$1" >/dev/null; }

# wait_healthy <service> [timeout_s]: waits for the compose healthcheck.
wait_healthy() {
  local svc="$1" timeout="${2:-120}" cid status
  cid="$(dc ps -q "$svc")"
  for _ in $(seq 1 "$timeout"); do
    status="$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$cid" 2>/dev/null || echo unknown)"
    if [ "$status" = "healthy" ] || [ "$status" = "running" ]; then
      return 0
    fi
    sleep 1
  done
  return 1
}

# ---------------------------------------------------------------- seed / api

ensure_seed() {
  if [ ! -s "$SEED_FILE" ]; then
    log "no seed file, seeding via REST API"
    python3 "$REPO_ROOT/loadtest/seed.py" --base-url "$BASE_URL" --out "$SEED_FILE"
  fi
  API_KEY="$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["api_key"])' "$SEED_FILE")"
  EXPERIMENT_KEY="$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["experiment_keys"][0])' "$SEED_FILE")"
  export API_KEY EXPERIMENT_KEY
}

# jwt_token: dashboard token for the seeded user
jwt_token() {
  local body
  body="$(python3 -c 'import json,sys;d=json.load(open(sys.argv[1]));print(json.dumps({"email":d["email"],"password":d["password"]}))' "$SEED_FILE")"
  curl -fsS -X POST "$BASE_URL/api/v1/auth/token/" -H 'Content-Type: application/json' -d "$body" \
    | python3 -c 'import json,sys;print(json.load(sys.stdin)["access"])'
}

# http_code <curl args...>: prints the status code (000 on connection failure)
http_code() {
  curl -s -o /dev/null -m 5 -w '%{http_code}' "$@" || true
}

evaluate_code() {
  http_code -X POST "$BASE_URL/api/v1/evaluate/" \
    -H "X-API-Key: $API_KEY" -H 'Content-Type: application/json' \
    -d "{\"user_id\":\"chaos-${1:-u1}\",\"experiment_keys\":[\"$EXPERIMENT_KEY\"]}"
}

# track_code <event_id> [user]
track_code() {
  http_code -X POST "$BASE_URL/api/v1/events/track/" \
    -H "X-API-Key: $API_KEY" -H 'Content-Type: application/json' \
    -d "{\"event_id\":\"$1\",\"user_id\":\"${2:-chaos-user}\",\"event_name\":\"chaos_test\",\"value\":1}"
}

# send_events <prefix> <count>: tracks <count> unique events, prints how many got 202
send_events() {
  local prefix="$1" count="$2" ok=0 code
  for i in $(seq 1 "$count"); do
    code="$(track_code "${prefix}-${i}")"
    [ "$code" = "202" ] && ok=$((ok + 1))
  done
  echo "$ok"
}

# wait_for_code <expected> <timeout_s> <fn> [args]: seconds until fn prints expected, or -1
wait_for_code() {
  local expected="$1" timeout="$2"; shift 2
  local start now
  start="$(date +%s)"
  while :; do
    if [ "$("$@")" = "$expected" ]; then
      now="$(date +%s)"; echo $((now - start)); return 0
    fi
    now="$(date +%s)"
    if [ $((now - start)) -ge "$timeout" ]; then echo -1; return 1; fi
    sleep 1
  done
}

# ---------------------------------------------------------------- background load

LOAD_PIDS=()
LOAD_FILE=""

# load_start <name>: LOAD_WORKERS curl loops against /evaluate, status codes to a file
load_start() {
  LOAD_FILE="$RESULTS_DIR/${1}-${RUN_ID}.codes"
  : > "$LOAD_FILE"
  log "background load: $LOAD_WORKERS workers -> $LOAD_FILE"
  for w in $(seq 1 "$LOAD_WORKERS"); do
    (
      n=0
      while :; do
        n=$((n + 1))
        printf '%s %s\n' "$(date +%s)" "$(evaluate_code "w${w}-${n}")" >> "$LOAD_FILE"
        sleep 0.05
      done
    ) &
    LOAD_PIDS+=("$!")
  done
}

load_stop() {
  if [ "${#LOAD_PIDS[@]}" -gt 0 ]; then
    kill "${LOAD_PIDS[@]}" 2>/dev/null || true
    wait "${LOAD_PIDS[@]}" 2>/dev/null || true
    LOAD_PIDS=()
  fi
}

# load_summary: status-code histogram of the background load
load_summary() {
  [ -n "$LOAD_FILE" ] && [ -s "$LOAD_FILE" ] || { info "no load samples"; return; }
  info "evaluate status codes during scenario (count code):"
  awk '{print $2}' "$LOAD_FILE" | sort | uniq -c | sed 's/^/         /'
}

# load_count_since <epoch> <code>: requests with <code> at/after epoch
load_count_since() {
  awk -v t="$1" -v c="$2" '$1 >= t && $2 == c {n++} END {print n+0}' "$LOAD_FILE"
}

trap 'load_stop' EXIT

# ---------------------------------------------------------------- data stores

ch_query() {
  dc exec -T clickhouse clickhouse-client --database experimentos -q "$1"
}

ch_count_prefix() {
  ch_query "SELECT count() FROM conversion_events WHERE event_id LIKE '${1}-%'"
}

# wait_ch_count <prefix> <expected> <timeout_s>: prints final count
wait_ch_count() {
  local prefix="$1" expected="$2" timeout="$3" count=0
  for _ in $(seq 1 "$timeout"); do
    count="$(ch_count_prefix "$prefix" 2>/dev/null || echo 0)"
    [ "$count" -ge "$expected" ] && break
    sleep 1
  done
  echo "$count"
}

redis_exists() {
  dc exec -T redis redis-cli EXISTS "$1" | tr -d '\r'
}

# consumer_metric <result>: events_consumed_total for conversion-events with result label
consumer_metric() {
  dc exec -T event-consumer python -c "
import urllib.request,sys
body=urllib.request.urlopen('http://localhost:9100/metrics',timeout=3).read().decode()
tot=0.0
for line in body.splitlines():
    if line.startswith('events_consumed_total{') and 'topic=\"conversion-events\"' in line and 'result=\"$1\"' in line:
        tot+=float(line.rsplit(' ',1)[1])
print(int(tot))
" 2>/dev/null || echo "n/a"
}
