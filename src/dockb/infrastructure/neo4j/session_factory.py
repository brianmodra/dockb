"""Factory and lifecycle manager for Neo4j sessions."""

from collections.abc import Generator
from contextlib import contextmanager

from neo4j import GraphDatabase, NotificationDisabledClassification, Session

# A young database has none of the MENTIONS graph yet, so every query that
# optionally reads it reports "the relationship type / property does not
# exist". That is an UNRECOGNIZED notification, not a fault: the queries all
# coalesce the absent values, so the class is silenced and the other
# severities keep announcing themselves.
_DISABLED_NOTIFICATIONS = [NotificationDisabledClassification.UNRECOGNIZED]


class SessionFactory:
    """Wraps a ``neo4j.Driver`` and provides contextual session creation."""

    def __init__(self, uri: str, user: str, password: str) -> None:
        self._driver = GraphDatabase.driver(
            uri,
            auth=(user, password),
            notifications_disabled_classifications=_DISABLED_NOTIFICATIONS,
        )
        self._closed = False

    @contextmanager
    def session(self) -> Generator[Session, None, None]:
        """Yield a :class:`neo4j.Session` obtained from the internal driver."""
        with self._driver.session() as session:
            yield session

    def close(self) -> None:
        """Release the underlying driver and its connection pool."""
        if self._closed:
            return
        self._closed = True
        self._driver.close()
