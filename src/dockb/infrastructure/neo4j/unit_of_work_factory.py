"""Factory for creating and managing UnitOfWork lifecycle."""

from typing import Any

from dockb.infrastructure.neo4j.serialized_session import SessionLike
from dockb.infrastructure.neo4j.session_factory import SessionFactory
from dockb.infrastructure.neo4j.unit_of_work import UnitOfWork, session_from_repos
from dockb.models.base import DockbModel


class UnitOfWorkFactory:
    """Manages the current UnitOfWork and creates fresh ones after commit."""

    def __init__(
        self,
        repos: dict[type[DockbModel], Any],
        session_factory: SessionFactory,
        reconstructor: Any,
        session: SessionLike | None = None,
    ) -> None:
        self._repos = repos
        self._session_factory = session_factory
        self._reconstructor = reconstructor
        self._session = session if session is not None else session_from_repos(repos)
        self._current: UnitOfWork | None = None

    def get_unit_of_work(self) -> UnitOfWork:
        """Return the current UnitOfWork, creating one if necessary."""
        if self._current is None:
            self._current = UnitOfWork(
                repos=self._repos,
                reconstructor=self._reconstructor,
                on_commit=self._on_committed,
                session=self._session,
            )
        return self._current

    def get_current_unit_of_work(self) -> UnitOfWork | None:
        """Return the current UnitOfWork or None if none is active."""
        return self._current

    def _on_committed(self) -> None:
        """Called by a UnitOfWork after a successful commit."""
        self._current = None
