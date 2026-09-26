import json
import logging
import threading
import time
from dataclasses import dataclass
from datetime import datetime

from django.conf import settings

logger = logging.getLogger(__name__)

_session = None
_circuit_open_until = 0.0
_session_lock = threading.Lock()
CIRCUIT_BREAK_SECONDS = 30.0


@dataclass
class StickyAssignment:
    user_id: str
    experiment_id: str
    variant_key: str
    variant_payload: dict
    bucket: int
    version_number: int
    assigned_at: datetime


def _is_enabled():
    return getattr(settings, "CASSANDRA_STICKY_ENABLED", True)


class StickyStoreUnavailableError(Exception):
    pass


def _get_session():
    """
    Lazy-initialize a Cassandra session (singleton).

    A failed connect opens a circuit for CIRCUIT_BREAK_SECONDS so evaluations
    don't each pay the connect timeout while Cassandra is down; they fall back
    to deterministic bucketing, which returns the same variant for most users.
    """
    global _session, _circuit_open_until
    if _session is not None:
        return _session
    if time.monotonic() < _circuit_open_until:
        raise StickyStoreUnavailableError("Cassandra circuit open")
    with _session_lock:
        if _session is None:
            _session = _connect()
    return _session


def _connect():
    global _circuit_open_until

    from cassandra.cluster import Cluster
    from cassandra.policies import DCAwareRoundRobinPolicy

    cluster = Cluster(
        contact_points=settings.CASSANDRA_CONTACT_POINTS,
        port=settings.CASSANDRA_PORT,
        # Empty CASSANDRA_LOCAL_DC lets the driver take the DC of the first contact point.
        load_balancing_policy=DCAwareRoundRobinPolicy(local_dc=settings.CASSANDRA_LOCAL_DC or None),
        connect_timeout=getattr(settings, "CASSANDRA_CONNECT_TIMEOUT", 2.0),
    )
    try:
        return cluster.connect(settings.CASSANDRA_KEYSPACE)
    except Exception:
        _circuit_open_until = time.monotonic() + CIRCUIT_BREAK_SECONDS
        cluster.shutdown()
        raise


def get_sticky_assignment(user_id, experiment_id):
    """
    Look up a sticky assignment from Cassandra.
    Returns StickyAssignment on hit, None on miss or error.
    """
    if not _is_enabled():
        return None
    try:
        session = _get_session()
        query = (
            "SELECT user_id, experiment_id, variant_key, variant_payload, "
            "bucket, version_number, assigned_at "
            "FROM sticky_assignments WHERE user_id = %s AND experiment_id = %s"
        )
        row = session.execute(query, (user_id, experiment_id)).one()
        if row:
            return StickyAssignment(
                user_id=row.user_id,
                experiment_id=row.experiment_id,
                variant_key=row.variant_key,
                variant_payload=json.loads(row.variant_payload) if row.variant_payload else {},
                bucket=row.bucket,
                version_number=row.version_number,
                assigned_at=row.assigned_at,
            )
    except Exception:
        logger.warning("Cassandra read failed for sticky assignment", exc_info=True)
    return None


def save_sticky_assignment(user_id, experiment_id, variant_key, variant_payload, bucket, version_number):
    """Persist a sticky assignment to Cassandra. Fire-and-forget on error."""
    if not _is_enabled():
        return
    try:
        session = _get_session()
        query = (
            "INSERT INTO sticky_assignments "
            "(user_id, experiment_id, variant_key, variant_payload, bucket, version_number, assigned_at) "
            "VALUES (%s, %s, %s, %s, %s, %s, toTimestamp(now()))"
        )
        session.execute(query, (
            user_id,
            experiment_id,
            variant_key,
            json.dumps(variant_payload),
            bucket,
            version_number,
        ))
    except Exception:
        logger.warning("Cassandra write failed for sticky assignment", exc_info=True)


def delete_sticky_assignment(user_id, experiment_id):
    """Delete a sticky assignment for a specific user + experiment."""
    if not _is_enabled():
        return
    try:
        session = _get_session()
        query = "DELETE FROM sticky_assignments WHERE user_id = %s AND experiment_id = %s"
        session.execute(query, (user_id, experiment_id))
    except Exception:
        logger.warning("Cassandra delete failed for sticky assignment", exc_info=True)


def ensure_schema():
    """Create keyspace and table if they don't exist. Called during app startup or management command."""
    if not _is_enabled():
        logger.info("Cassandra sticky bucketing is disabled, skipping schema setup.")
        return

    try:
        from cassandra.cluster import Cluster

        cluster = Cluster(
            contact_points=settings.CASSANDRA_CONTACT_POINTS,
            port=settings.CASSANDRA_PORT,
        )
        session = cluster.connect()

        session.execute(f"""
            CREATE KEYSPACE IF NOT EXISTS {settings.CASSANDRA_KEYSPACE}
            WITH replication = {{'class': 'SimpleStrategy', 'replication_factor': 1}}
        """)

        session.set_keyspace(settings.CASSANDRA_KEYSPACE)

        session.execute("""
            CREATE TABLE IF NOT EXISTS sticky_assignments (
                user_id text,
                experiment_id text,
                variant_key text,
                variant_payload text,
                bucket int,
                version_number int,
                assigned_at timestamp,
                PRIMARY KEY ((user_id, experiment_id))
            )
        """)

        cluster.shutdown()
        logger.info("Cassandra schema created successfully.")
    except Exception:
        logger.warning("Cassandra schema setup failed", exc_info=True)
