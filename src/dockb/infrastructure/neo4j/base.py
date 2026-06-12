"""Abstract base class for Neo4j repository classes."""

from abc import ABC, abstractmethod
from typing import Any, Generic, TypeVar

from neo4j import Session

from dockb.models.base import DataState, DockbModel

M = TypeVar("M", bound=DockbModel)


class BaseRepository(ABC, Generic[M]):  # pylint: disable=too-few-public-methods
    """Shared save dispatch for models with DataState.

    Concrete subclasses must provide ``_new_cypher``, ``_changed_cypher``,
    ``_delete_cypher`` properties and a ``_build_params`` method.
    """

    def __init__(self, session: Session) -> None:
        self._session = session

    def save(self, model: M, **parent_ids: str) -> None:
        """Persist *model* based on its DataState."""
        if model.dirty:
            raise ValueError(f"{type(model).__name__} is dirty, cannot save")

        match model.state:
            case DataState._ | DataState.SYNC:
                return
            case DataState.NEW:
                self._session.run(self._new_cypher, self._build_params(model, **parent_ids))
            case DataState.CHANGED:
                self._session.run(self._changed_cypher, self._build_params(model, **parent_ids))
            case DataState.DELETED:
                self._session.run(
                    self._delete_cypher,
                    self._build_params(model, **parent_ids),
                )

    @property
    @abstractmethod
    def _new_cypher(self) -> str: ...

    @property
    @abstractmethod
    def _changed_cypher(self) -> str: ...

    @property
    @abstractmethod
    def _delete_cypher(self) -> str: ...

    @abstractmethod
    def _build_params(self, model: M, **parent_ids: str) -> dict[str, Any]:
        """Return the Cypher parameters dict for *model*."""
