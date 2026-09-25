# ADR 0002: Deterministic MurmurHash bucketing and a separate rollout gate

**Status:** Accepted

## Decision
- Variant bucket: `murmur3("{user_id}:{experiment_key}:{version}") % 10000`. Including the version
  lets a new version re-randomize when needed; sticky bucketing (ADR 0003) protects existing users.
- Live rollout: an independent bucket `murmur3("{user_id}:{experiment_key}:rollout") % 10000`
  compared with `Experiment.rollout_percentage`, checked before the sticky lookup.
- `traffic_allocation` stays on the immutable, locked version; `rollout_percentage` is the only
  knob that changes while running.

## Why
The rollout hash omits the version, so cohorts are nested: 10% ⊂ 25% ⊂ 50% ⊂ 100%, and a rollback
from 50% to 10% returns exactly the original 10%. Checking the gate before sticky lookup means a
rollback actually removes users from the variant instead of being bypassed by stickiness.
MurmurHash3 is fast, uniform, and available in every SDK language.
