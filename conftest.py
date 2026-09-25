from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import factory
import fakeredis
import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from apps.accounts.models import APIKey
from apps.experiments.models import (
    Experiment,
    ExperimentStatus,
    ExperimentType,
    ExperimentVersion,
    TargetingRule,
    Variant,
)
from apps.organizations.models import Organization, Project

User = get_user_model()


# ── Factories ──


class UserFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = User
        skip_postgeneration_save = True

    email = factory.Sequence(lambda n: f"user{n}@example.com")
    username = factory.Sequence(lambda n: f"user{n}")
    password = factory.PostGenerationMethodCall("set_password", "testpass123")

    @factory.post_generation
    def _save_password(self, create, extracted, **kwargs):
        if create:
            self.save()


class OrganizationFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Organization

    name = factory.Sequence(lambda n: f"Organization {n}")
    slug = factory.Sequence(lambda n: f"org-{n}")


class ProjectFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Project

    organization = factory.SubFactory(OrganizationFactory)
    name = factory.Sequence(lambda n: f"Project {n}")
    slug = factory.Sequence(lambda n: f"project-{n}")


class ExperimentFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Experiment

    project = factory.SubFactory(ProjectFactory)
    key = factory.Sequence(lambda n: f"experiment-{n}")
    name = factory.Sequence(lambda n: f"Experiment {n}")
    status = ExperimentStatus.DRAFT
    experiment_type = ExperimentType.AB


class ExperimentVersionFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = ExperimentVersion

    experiment = factory.SubFactory(ExperimentFactory)
    version_number = 1
    traffic_allocation = 10000


class VariantFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Variant

    version = factory.SubFactory(ExperimentVersionFactory)
    key = factory.Sequence(lambda n: f"variant-{n}")
    name = factory.Sequence(lambda n: f"Variant {n}")
    traffic_percentage = 5000
    bucket_start = 0
    bucket_end = 4999


class TargetingRuleFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = TargetingRule

    version = factory.SubFactory(ExperimentVersionFactory)
    rules_json = {}


# ── Fixtures ──


@pytest.fixture(autouse=True)
def clear_django_cache():
    """Throttle counters live in the Django cache; isolate them per test."""
    from django.core.cache import cache

    cache.clear()
    yield


@pytest.fixture(autouse=True)
def fake_redis():
    """Replace Redis client with fakeredis for all tests."""
    server = fakeredis.FakeServer()
    client = fakeredis.FakeRedis(server=server, decode_responses=True)
    with patch("apps.engine.cache.get_redis_client", return_value=client):
        with patch("apps.engine.locks.get_redis_client", return_value=client):
            with patch("apps.events.consumer.get_redis_client", return_value=client):
                yield client


@pytest.fixture(autouse=True)
def mock_kafka():
    """Disable Kafka producer in all tests."""
    mock_producer = MagicMock()
    mock_producer.produce = MagicMock()
    mock_producer.poll = MagicMock()
    mock_producer.flush = MagicMock()
    with patch("apps.events.producer._get_producer", return_value=mock_producer):
        yield mock_producer


@pytest.fixture(autouse=True)
def mock_clickhouse():
    """Disable ClickHouse in all tests. Returns a mock client."""
    mock_client = MagicMock()
    mock_client.insert = MagicMock()
    mock_client.query = MagicMock(return_value=MagicMock(result_rows=[]))
    mock_client.command = MagicMock()
    with patch("apps.events.clickhouse.get_clickhouse_client", return_value=mock_client):
        with patch("apps.observability.telemetry.get_clickhouse_client", return_value=mock_client):
            yield mock_client


@pytest.fixture
def mock_cassandra(monkeypatch):
    """Mock Cassandra sticky operations for tests that need them."""
    from apps.engine.sticky import StickyAssignment

    store = {}

    def mock_get(user_id, experiment_id):
        return store.get((user_id, experiment_id))

    def mock_save(user_id, experiment_id, variant_key, variant_payload, bucket, version_number):
        store[(user_id, experiment_id)] = StickyAssignment(
            user_id=user_id,
            experiment_id=experiment_id,
            variant_key=variant_key,
            variant_payload=variant_payload,
            bucket=bucket,
            version_number=version_number,
            assigned_at=datetime.now(timezone.utc),
        )

    def mock_delete(user_id, experiment_id):
        store.pop((user_id, experiment_id), None)

    monkeypatch.setattr("apps.engine.assigner.get_sticky_assignment", mock_get)
    monkeypatch.setattr("apps.engine.assigner.save_sticky_assignment", mock_save)
    return store


@pytest.fixture
def user(db):
    return UserFactory()


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def authenticated_client(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


@pytest.fixture
def organization(user):
    """An organization in which the default `user` is an ADMIN."""
    from apps.organizations.models import Membership, Role

    org = OrganizationFactory()
    Membership.objects.create(organization=org, user=user, role=Role.ADMIN)
    return org


@pytest.fixture
def make_member(organization):
    """Create a user with the given role in `organization`, returning an authenticated client."""
    from apps.organizations.models import Membership

    def _make(role):
        member = UserFactory()
        Membership.objects.create(organization=organization, user=member, role=role)
        client = APIClient()
        client.force_authenticate(user=member)
        return client

    return _make


@pytest.fixture
def project(organization):
    return ProjectFactory(organization=organization)


@pytest.fixture
def api_key(project, user):
    """Create an API key and return (APIKey instance, raw_key)."""
    raw_key, prefix, hashed = APIKey.generate_key("test")
    key = APIKey.objects.create(
        key_prefix=prefix,
        hashed_key=hashed,
        name="Test Key",
        project=project,
        created_by=user,
    )
    return key, raw_key


@pytest.fixture
def running_experiment(project, user):
    """Create a fully configured running experiment with control + treatment."""
    experiment = ExperimentFactory(
        project=project,
        key="test-experiment",
        owner=user,
        status=ExperimentStatus.DRAFT,
    )
    version = ExperimentVersionFactory(
        experiment=experiment,
        version_number=1,
        traffic_allocation=10000,
    )
    VariantFactory(
        version=version,
        key="control",
        name="Control",
        is_control=True,
        traffic_percentage=5000,
        bucket_start=0,
        bucket_end=4999,
    )
    VariantFactory(
        version=version,
        key="treatment",
        name="Treatment",
        is_control=False,
        traffic_percentage=5000,
        bucket_start=5000,
        bucket_end=9999,
    )
    experiment.current_version = version
    experiment.status = ExperimentStatus.RUNNING
    experiment.save()
    version.is_active = True
    version.is_locked = True
    version.save()
    return experiment
