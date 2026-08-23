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
