"""Abstract base class for Neo4j repository classes."""

import logging
from abc import ABC, abstractmethod
from typing import Any, Generic, TypeVar

from neo4j import Session

from dockb.models.base import DataState, DockbModel

logger = logging.getLogger(__name__)

M = TypeVar("M", bound=DockbModel)


class BaseRepository(ABC, Generic[M]):  # pylint: disable=too-few-public-methods
    """Shared save dispatch for models with DataState.

    Concrete subclasses must provide ``_new_cypher``, ``_changed_cypher``,
    ``_delete_cypher`` properties and a ``_build_params`` method.
    """

    def __init__(self, session: Session) -> None:
        self._session = session

    @staticmethod
    def _child_count(model: M) -> int:
        """Count the immediate children of *model*, regardless of concrete type."""
        for field in ("chapters", "paragraphs", "sentences", "tokens"):
            children = getattr(model, field, None)
            if children is not None:
                return len(children)
        return 0

    def save(self, model: M, **parent_ids: str) -> None:
        """Persist *model* based on its DataState."""
        if model.dirty:
            raise ValueError(f"{type(model).__name__} is dirty, cannot save")

        match model.state:
            case DataState._ | DataState.SYNC:
                logger.debug("Skip %s (state=%s)", type(model).__name__, model.state.value)
                return
            case DataState.NEW:
                logger.debug("Create %s (%d children)", type(model).__name__, self._child_count(model))
                self._session.run(self._new_cypher, self._build_params(model, **parent_ids))
            case DataState.CHANGED:
                logger.debug("Update %s (%d children)", type(model).__name__, self._child_count(model))
                self._session.run(self._changed_cypher, self._build_params(model, **parent_ids))
            case DataState.DELETED:
                logger.debug("Delete %s", type(model).__name__)
                self._session.run(self._delete_cypher, self._build_params(model, **parent_ids))

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
