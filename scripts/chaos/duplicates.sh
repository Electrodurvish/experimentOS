#!/usr/bin/env bash
# Scenario: the same event is delivered many times (SDK retries, producer
# retries, consumer re-delivery after a crash).
#
# Expected (from code): the API accepts every copy (it does not dedup,
# apps/events/views.py); the consumer's Redis SETNX on dedup:<event_id>
# (apps/events/consumer.py:16-30, TTL EVENT_DEDUP_TTL=24h) lets exactly one copy
# through, so ClickHouse holds exactly one row per event_id. Dedup is keyed on
# event_id only (not on event name/user), and only lasts 24h.
# shellcheck source=lib.sh disable=SC2015
source "$(dirname "$0")/lib.sh"

COPIES="${COPIES:-20}"
EVENTS="${EVENTS:-10}"
PREFIX="chaos-dup-$RUN_ID"

ensure_seed
log "sending $EVENTS distinct events x $COPIES copies each"
for e in $(seq 1 "$EVENTS"); do
  for _ in $(seq 1 "$COPIES"); do
    track_code "${PREFIX}-${e}" >/dev/null
  done
done

count="$(wait_ch_count "$PREFIX" "$EVENTS" 60)"
sleep 5
count="$(ch_count_prefix "$PREFIX")"
if [ "$count" -eq "$EVENTS" ]; then
  pass "exactly $EVENTS rows for $EVENTS event_ids ($((EVENTS * COPIES)) deliveries)"
else
  fail "$count rows for $EVENTS event_ids (expected $EVENTS)"
fi
info "consumer duplicate counter (since last consumer start): $(consumer_metric duplicate)"

log "same, with Redis down (dedup fails open by design)"
PREFIX2="chaos-dup-noredis-$RUN_ID"
service_stop redis
for _ in $(seq 1 "$COPIES"); do track_code "${PREFIX2}-1" >/dev/null; done
sleep 10
service_start redis
wait_healthy redis 60 || true
count2="$(ch_count_prefix "$PREFIX2")"
info "rows for one event_id sent $COPIES times with Redis down: $count2"
info "(0 = the API itself failed without Redis - see kill-redis.sh throttling note; >1 = duplicates stored)"

finish
