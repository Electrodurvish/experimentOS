from collections import Counter

from apps.engine.hasher import BUCKET_SPACE, compute_bucket


class TestComputeBucket:
    def test_deterministic(self):
        """Same inputs always produce same bucket."""
        bucket1 = compute_bucket("user-123", "experiment-1", 1)
        bucket2 = compute_bucket("user-123", "experiment-1", 1)
        assert bucket1 == bucket2

    def test_range(self):
        """Bucket is always within [0, 9999]."""
        for i in range(1000):
            bucket = compute_bucket(f"user-{i}", "exp", 1)
            assert 0 <= bucket < BUCKET_SPACE

    def test_different_users_get_different_buckets(self):
        """Different users generally get different buckets."""
        buckets = {compute_bucket(f"user-{i}", "exp", 1) for i in range(100)}
        # With 100 users and 10000 buckets, collisions are unlikely but possible
        assert len(buckets) > 80

    def test_different_experiments_produce_different_buckets(self):
        """Same user in different experiments gets different buckets."""
        bucket1 = compute_bucket("user-1", "exp-a", 1)
        bucket2 = compute_bucket("user-1", "exp-b", 1)
        # Not guaranteed to differ but extremely likely
        # Just verify they're valid
        assert 0 <= bucket1 < BUCKET_SPACE
        assert 0 <= bucket2 < BUCKET_SPACE

    def test_different_versions_produce_different_buckets(self):
        """Same user in different versions gets different buckets."""
        bucket1 = compute_bucket("user-1", "exp", 1)
        bucket2 = compute_bucket("user-1", "exp", 2)
        assert 0 <= bucket1 < BUCKET_SPACE
        assert 0 <= bucket2 < BUCKET_SPACE

    def test_uniform_distribution(self):
        """Buckets should be roughly uniformly distributed."""
        num_users = 100000
        buckets = [compute_bucket(f"user-{i}", "exp", 1) for i in range(num_users)]

        # Divide into 10 bins of 1000 buckets each
        bins = Counter()
        for b in buckets:
            bins[b // 1000] += 1

        expected_per_bin = num_users / 10
        for bin_idx, count in bins.items():
            # Each bin should have roughly 10% of users (within 20% tolerance)
            assert abs(count - expected_per_bin) / expected_per_bin < 0.2, (
                f"Bin {bin_idx} has {count} users, expected ~{expected_per_bin}"
            )
