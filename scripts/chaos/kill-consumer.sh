#!/usr/bin/env bash
# Scenario: Kafka consumer crashes (SIGKILL) while events keep arriving.
#
# Expected (from code, apps/events/consumer.py as of commit 2360466):
#   - The API keeps accepting events (202): it only produces to Kafka
#     (apps/events/views.py TrackEventView -> apps/events/producer.py).
#   - Events accumulate in Kafka; after restart the consumer group resumes from
#     its last committed offset and stores them. Offsets are committed manually
#     after each successful insert (enable.auto.commit=False, consumer.py:158-163,
#     commit at consumer.py:130), so un-committed messages are re-delivered.
#   - A re-delivered message that was already stored is skipped by the Redis
#     SETNX dedup key (consumer.py:35-48, 66-69), so no duplicate rows.
#   - Remaining gap: the dedup key is set BEFORE the insert (consumer.py:66-76)
#     and only released if the insert raises. A SIGKILL after SETNX but before
#     the insert completes leaves the key set, so the re-delivered message is
#     skipped as a "duplicate" and that event is lost (window: one in-flight
#     message per partition). This script cannot hit that window deterministically.
# shellcheck source=lib.sh disable=SC2015
source "$(dirname "$0")/lib.sh"

N="${N:-200}"
PREFIX="chaos-consumer-$RUN_ID"

ensure_seed
log "scenario: kill event-consumer, send $N events, restart, verify all arrive in ClickHouse"

dup_before="$(consumer_metric duplicate)"
service_kill event-consumer

log "sending $N events while the consumer is down"
accepted="$(send_events "$PREFIX" "$N")"
if [ "$accepted" -eq "$N" ]; then pass "API accepted $accepted/$N events with consumer down"; else fail "API accepted only $accepted/$N"; fi

sleep 5
in_ch="$(ch_count_prefix "$PREFIX")"
info "rows in ClickHouse while consumer down: $in_ch (expected 0)"

service_start event-consumer
t0="$(date +%s)"
final="$(wait_ch_count "$PREFIX" "$N" 120)"
t1="$(date +%s)"
if [ "$final" -eq "$N" ]; then
  pass "all $N events processed after restart (catch-up took ~$((t1 - t0))s)"
else
  fail "only $final/$N events reached ClickHouse within 120s of restart"
fi

dup_after="$(consumer_metric duplicate)"
info "consumer duplicate counter: before=$dup_before after=$dup_after (process restarted, counter resets)"
info "extra rows (would indicate duplicates not caught): $(( $(ch_count_prefix "$PREFIX") - N ))"

finish
