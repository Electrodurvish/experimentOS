#!/usr/bin/env bash
# Start the full ExperimentOS stack with demo data and open the dashboard.
#   scripts/demo.sh          start (or reuse) and seed
#   scripts/demo.sh down     stop and delete demo data
set -euo pipefail
cd "$(dirname "$0")/.."

COMPOSE=(docker compose -p experimentos-demo -f docker-compose.yml -f docker-compose.demo.yml)
SERVICES=(db redis cassandra kafka clickhouse rabbitmq api event-consumer celery-worker celery-beat frontend)

if [[ "${1:-}" == "down" ]]; then
  "${COMPOSE[@]}" down -v
  exit 0
fi

echo "Building and starting containers (first run takes a few minutes; Cassandra is slow to boot)..."
"${COMPOSE[@]}" up -d --build "${SERVICES[@]}"
python3 scripts/demo_data.py --base-url http://localhost:8000 "$@"
