import pytest

from apps.engine.cache import (
    cache_experiment_config,
    get_cached_experiment_config,
    invalidate_experiment_config,
    invalidate_project_experiments,
    serialize_experiment_config,
)


class TestExperimentConfigCache:
    def test_cache_miss_returns_none(self):
        result = get_cached_experiment_config("project-1", "exp-1")
        assert result is None

    def test_cache_hit_returns_config(self):
        config = {"id": "123", "key": "exp-1", "status": "RUNNING"}
        cache_experiment_config("project-1", "exp-1", config)
        result = get_cached_experiment_config("project-1", "exp-1")
        assert result == config

    def test_different_projects_isolated(self):
        config1 = {"id": "1", "key": "exp-1"}
        config2 = {"id": "2", "key": "exp-1"}
        cache_experiment_config("project-1", "exp-1", config1)
        cache_experiment_config("project-2", "exp-1", config2)

        assert get_cached_experiment_config("project-1", "exp-1") == config1
        assert get_cached_experiment_config("project-2", "exp-1") == config2

    def test_invalidate_specific_experiment(self):
        cache_experiment_config("project-1", "exp-1", {"id": "1"})
        cache_experiment_config("project-1", "exp-2", {"id": "2"})

        invalidate_experiment_config("project-1", "exp-1")

        assert get_cached_experiment_config("project-1", "exp-1") is None
        assert get_cached_experiment_config("project-1", "exp-2") is not None

    def test_invalidate_project_experiments(self):
        cache_experiment_config("project-1", "exp-1", {"id": "1"})
        cache_experiment_config("project-1", "exp-2", {"id": "2"})
        cache_experiment_config("project-2", "exp-3", {"id": "3"})

        invalidate_project_experiments("project-1")

        assert get_cached_experiment_config("project-1", "exp-1") is None
        assert get_cached_experiment_config("project-1", "exp-2") is None
        assert get_cached_experiment_config("project-2", "exp-3") is not None


@pytest.mark.django_db
class TestSerializeExperimentConfig:
    def test_serialize_running_experiment(self, running_experiment):
        config = serialize_experiment_config(running_experiment)

        assert config["id"] == str(running_experiment.id)
        assert config["key"] == "test-experiment"
        assert config["status"] == "RUNNING"
        assert config["current_version"] is not None
        assert config["current_version"]["version_number"] == 1
        assert config["current_version"]["traffic_allocation"] == 10000
        assert len(config["current_version"]["variants"]) == 2

        variant_keys = {v["key"] for v in config["current_version"]["variants"]}
        assert variant_keys == {"control", "treatment"}

    def test_serialize_experiment_no_version(self):
        from conftest import ExperimentFactory

        exp = ExperimentFactory()
        config = serialize_experiment_config(exp)
        assert config["current_version"] is None
