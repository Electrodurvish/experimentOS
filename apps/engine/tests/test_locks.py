import pytest

from apps.engine.locks import LockAcquisitionError, distributed_lock


class TestDistributedLock:
    def test_acquire_and_release(self, fake_redis):
        with distributed_lock("test-resource"):
            # Lock should be held
            assert fake_redis.exists("lock:test-resource")

        # Lock should be released
        assert not fake_redis.exists("lock:test-resource")

    def test_lock_prevents_double_acquisition(self, fake_redis):
        with distributed_lock("test-resource"):
            # Try to acquire the same lock — should fail
            with pytest.raises(LockAcquisitionError):
                with distributed_lock("test-resource", retry_count=1, retry_delay=0.01):
                    pass

    def test_different_resources_independent(self, fake_redis):
        with distributed_lock("resource-a"):
            # Acquiring a different resource should work
            with distributed_lock("resource-b"):
                assert fake_redis.exists("lock:resource-a")
                assert fake_redis.exists("lock:resource-b")

    def test_lock_released_on_exception(self, fake_redis):
        with pytest.raises(ValueError):
            with distributed_lock("test-resource"):
                raise ValueError("something broke")

        # Lock should still be released
        assert not fake_redis.exists("lock:test-resource")

    def test_lock_with_custom_ttl(self, fake_redis):
        with distributed_lock("test-resource", ttl=10):
            ttl = fake_redis.ttl("lock:test-resource")
            assert 0 < ttl <= 10
