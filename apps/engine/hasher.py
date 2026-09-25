import mmh3

BUCKET_SPACE = 10000


def compute_bucket(user_id: str, experiment_key: str, version_number: int) -> int:
    """
    Deterministic bucket assignment using MurmurHash3.

    Input: "{user_id}:{experiment_key}:{version_number}"
    Output: integer in range [0, 9999]

    Properties:
    - Deterministic: same input always produces same bucket
    - Uniform: roughly equal distribution across buckets
    - Fast: non-cryptographic hash, suitable for hot-path evaluation
    - Cross-platform: MurmurHash3 implementations exist in all major languages
    """
    hash_input = f"{user_id}:{experiment_key}:{version_number}"
    hash_value = mmh3.hash(hash_input, seed=0, signed=False)
    return hash_value % BUCKET_SPACE


def compute_rollout_bucket(user_id: str, experiment_key: str) -> int:
    """
    Bucket used for the experiment's live rollout gate.

    Deliberately independent of the version number, so that a user inside a
    10% rollout stays inside it at 25%, 50% and 100% (monotonic rollouts),
    and a rollback from 50% to 10% keeps exactly the original 10%.
    """
    hash_value = mmh3.hash(f"{user_id}:{experiment_key}:rollout", seed=0, signed=False)
    return hash_value % BUCKET_SPACE
