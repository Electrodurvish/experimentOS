# ADR 0006: Rule-based decision engine with evidence; AI only explains

**Status:** Accepted

## Decision
- `apps/decisions/engine.decide()` is a pure, deterministic function over plain inputs (stats,
  health, guardrails, telemetry, anomalies, segments, interactions). It returns a recommendation,
  a confidence, the checks it evaluated, and numbered evidence.
- Automated actions are gated by a per-experiment `RolloutPolicy` (auto_rollback, auto_advance,
  minimum confidence, minimum stage duration). `COMPLETE` is never automatic.
- The LLM receives only the evidence bundle and must cite evidence IDs. It never triggers actions.

## Why
Automated rollbacks must be explainable, reproducible and testable; a pure function is all three.
LLM output is useful for narrative explanations and ad-hoc questions but is not a safe control
signal. Template fallbacks keep explanations available without an API key.
