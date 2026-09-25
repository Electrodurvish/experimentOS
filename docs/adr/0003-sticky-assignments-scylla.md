# ADR 0003: Sticky assignments in ScyllaDB (Cassandra protocol)

**Status:** Accepted

## Context
Assignments must survive version changes and be looked up on every evaluation, keyed by
`(user_id, experiment_id)`, at a write rate proportional to traffic.

## Decision
Store sticky assignments in a ScyllaDB/Cassandra table partitioned by user and experiment.
PostgreSQL keeps an `Assignment` row for analytics and the debugger, but is not on the
read path for stickiness. Local development uses Cassandra 4.1 (same protocol).

## Consequences
- Single-partition reads/writes with predictable latency at high volume.
- Eventual consistency is acceptable: a lost sticky write just means the next evaluation recomputes
  the same deterministic bucket (ADR 0002), so users only move if bucket ranges changed.
