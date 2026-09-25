#!/usr/bin/env bash
# Scenario: the Kafka broker is down for a short time.
#
# Expected (from code):
#   - produce() only appends to librdkafka's local queue, so the API keeps
#     returning 202 (apps/events/producer.py:106-117). Delivery is retried in
#     the background; messages older than message.timeout.ms (librdkafka
#     default 300000 ms, not overridden in producer.py:30-36) are dropped and
#     only logged by _delivery_callback (producer.py:43-46).
#   - events_produced_total is incremented at enqueue time, not on delivery,
#     so the metric over-reports during an outage.
#   - Short outage (< 5 min): all events should arrive once Kafka is back.
#   - If the api process restarts during the outage, its queued events are
#     lost (no flush on shutdown).
# shellcheck source=lib.sh disable=SC2015
source "$(dirname "$0")/lib.sh"

N="${N:-100}"
OUTAGE="${OUTAGE:-20}"
PREFIX="chaos-kafka-$RUN_ID"

ensure_seed
service_stop kafka
log "sending $N events with the broker down"
accepted="$(send_events "$PREFIX" "$N")"
[ "$accepted" -eq "$N" ] && pass "API accepted $accepted/$N events (buffered in producer)" || fail "API accepted only $accepted/$N"
sleep "$OUTAGE"

service_start kafka
wait_healthy kafka 120 || fail "kafka did not become healthy"
final="$(wait_ch_count "$PREFIX" "$N" 120)"
[ "$final" -eq "$N" ] && pass "all $N buffered events delivered after broker recovery" \
  || fail "$final/$N events delivered within 120s of broker recovery"

finish
