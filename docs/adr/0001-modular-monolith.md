# ADR 0001: Modular Django monolith with separately scaled workers

**Status:** Accepted

## Context
The plan lists many logical services (experiment, assignment, analytics, health engine) and warns
against "random microservices". Most of these share the same configuration data and change together.

## Decision
One Django codebase split into apps with clear boundaries (`experiments`, `engine`, `events`,
`stats`, `intelligence`, `decisions`, `ai`, ...). Processes that scale differently run the same
image with different commands: `api` (gunicorn), `event-consumer`, `celery-worker`, `celery-beat`.

## Consequences
- One deploy artifact, one migration history, in-process calls between engines.
- The hot path (`/evaluate`) and the consumer scale independently through their own HPAs.
- If the assignment engine ever needs a different runtime, `apps/engine` is the extraction seam:
  it depends only on experiment configuration (already serialized for Redis) and ScyllaDB.
