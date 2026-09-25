#!/usr/bin/env bash
# Scenario: ClickHouse goes down while events flow.
#
# Expected (from code, apps/events/consumer.py as of commit 2360466):
#   - The API is unaffected (it only produces to Kafka).
#   - insert_conversion raises EventStoreError (apps/events/clickhouse.py:132-160);
#     the consumer releases the dedup key (consumer.py:71-76), rewinds the
#     partition to the failed offset (consumer.py:121-128) and retries with
#     exponential backoff capped at 30s (consumer.py:182-186). Nothing is
#     committed, so no event is lost; the partition is blocked until ClickHouse
#     returns, then catches up.
#   - events_consumed_total{result="failed"} increments on every retry. Because
#     the EventConsumerStalled alert (infra/prometheus/alerts.yml) sums all
#     results, these retries keep it from firing during exactly this outage.
#   - Dashboard results endpoints that query ClickHouse fail during the outage.
# shellcheck source=lib.sh disable=SC2015
source "$(dirname "$0")/lib.sh"

N="${N:-100}"
PREFIX_DURING="chaos-ch-during-$RUN_ID"
PREFIX_AFTER="chaos-ch-after-$RUN_ID"

ensure_seed
service_stop clickhouse

log "sending $N events while ClickHouse is down"
accepted="$(send_events "$PREFIX_DURING" "$N")"
[ "$accepted" -eq "$N" ] && pass "API accepted $accepted/$N events" || fail "API accepted only $accepted/$N"

# Give the consumer time to poll and fail on them.
sleep 15
info "consumer 'will retry' log lines in the last 60s: $(dc logs --since 60s event-consumer 2>&1 | grep -c 'will retry' || true)"
info "consumer failed-insert counter: $(consumer_metric failed)"
during_down="$(ch_count_prefix "$PREFIX_DURING" 2>/dev/null || echo 0)"
info "rows visible while ClickHouse down: ${during_down} (query fails -> 0)"

service_start clickhouse
wait_healthy clickhouse 90 || fail "clickhouse did not become healthy"
t0="$(date +%s)"

# Backoff is capped at 30s, so allow a generous window for the catch-up.
during="$(wait_ch_count "$PREFIX_DURING" "$N" 120)"
t1="$(date +%s)"
if [ "$during" -eq "$N" ]; then
  pass "all $N events sent during the outage stored after recovery (~$((t1 - t0))s after ClickHouse healthy)"
else
  fail "DATA LOSS or slow catch-up: $during/$N events from the outage stored within 120s"
fi

log "sending $N more events after recovery"
send_events "$PREFIX_AFTER" "$N" >/dev/null
after="$(wait_ch_count "$PREFIX_AFTER" "$N" 60)"
[ "$after" -eq "$N" ] && pass "post-recovery events all stored ($after/$N) without restarting the consumer" \
  || fail "post-recovery: only $after/$N stored"
extra="$(( $(ch_count_prefix "$PREFIX_DURING") - N ))"
[ "$extra" -le 0 ] && pass "no duplicate rows from the retries" || fail "$extra duplicate rows from retries"

finish
