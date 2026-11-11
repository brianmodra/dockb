"""Abstract base class for Neo4j repository classes."""

import logging
from abc import ABC, abstractmethod
from typing import Any, Generic, TypeVar

from dockb.infrastructure.neo4j.serialized_session import SessionLike
from dockb.models.base import DataState, DockbModel

logger = logging.getLogger(__name__)

M = TypeVar("M", bound=DockbModel)

_BATCH_SIZE = 500


class BaseRepository(ABC, Generic[M]):  # pylint: disable=too-few-public-methods
    """Shared save dispatch for models with DataState.

    Concrete subclasses must provide ``_new_cypher``, ``_changed_cypher``,
    ``_delete_cypher`` properties and a ``_build_params`` method.
    """

    def __init__(self, session: SessionLike) -> None:
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

    def save_many(self, entries: list[tuple[M, dict[str, str]]]) -> None:
        """Persist a batch of like-typed models in registration order.

        The default issues one :meth:`save` per entry; repositories whose write
        Cypher UNWINDs child rows override this to batch many models into a
        single query. Entries of a batch always share the repository (the unit
        of work dispatches by model type) but may span states."""
        for model, parent_ids in entries:
            self.save(model, **parent_ids)

    def _run_batched(self, cypher: str, rows: list[dict[str, Any]]) -> None:
        """Run *cypher* once per ``_BATCH_SIZE`` slice of *rows* under ``$rows``."""
        for start in range(0, len(rows), _BATCH_SIZE):
            self._session.run(cypher, {"rows": rows[start : start + _BATCH_SIZE]})

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
