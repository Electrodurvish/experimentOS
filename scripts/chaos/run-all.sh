#!/usr/bin/env bash
# Run every chaos scenario against the local docker-compose stack and write a
# combined log to scripts/chaos/results/. Scenarios are independent; a failed
# expectation does not stop the rest.
#
#   docker compose up -d
#   docker compose exec api python manage.py migrate
#   docker compose exec api python manage.py setup_clickhouse
#   docker compose exec api python manage.py setup_cassandra
#   scripts/chaos/run-all.sh
set -uo pipefail

DIR="$(cd "$(dirname "$0")" && pwd)"
mkdir -p "$DIR/results"
LOG="$DIR/results/run-all-$(date +%Y%m%d-%H%M%S).log"

scenarios=(duplicates kill-consumer kill-kafka kill-clickhouse kill-redis kill-postgres kill-api)
summary=""

for s in "${scenarios[@]}"; do
  echo "================ $s ================" | tee -a "$LOG"
  if "$DIR/$s.sh" 2>&1 | tee -a "$LOG"; then
    status="met"
  else
    status="NOT met"
  fi
  summary="${summary}$(printf '  %-16s %s' "$s" "$status")"$'\n'

  sleep 5
done

echo | tee -a "$LOG"
echo "Summary (expectations from code, see docs/failure-testing.md):" | tee -a "$LOG"
printf '%s' "$summary" | tee -a "$LOG"
echo "log: $LOG"
