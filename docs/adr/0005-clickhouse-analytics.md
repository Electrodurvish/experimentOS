# ADR 0005: ClickHouse for event analytics and production telemetry

**Status:** Accepted

## Decision
Exposures, conversions and per-variant production telemetry live in ClickHouse MergeTree tables.
Experiment results are computed in a single query: each user is attributed to the variant of their
first exposure, and counts as converted if a (primary-metric) conversion occurs at or after it.

## Why
Aggregations over millions of rows per experiment (unique users, quantiles, time buckets) are what
columnar storage is for. Keeping computation in ClickHouse avoids moving user IDs into Python.

## Consequences
- ClickHouse is not the source of truth for configuration; PostgreSQL is.
- Inserts are currently one row per event from the consumer; batching inserts is the next
  throughput step (see failure-testing and load-testing docs).
