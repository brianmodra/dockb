"""Unit of Work — tracks models to persist and dispatches them to repositories."""

from typing import Any

from dockb.infrastructure.neo4j.base import BaseRepository
from dockb.models.base import DataState, DockbModel

# Model type name → required parent_id key for Cypher relationship matching.
# Document is top-level and needs no parent.
_PARENT_REQUIREMENTS: dict[str, str] = {
    "Chapter": "document_id",
    "Paragraph": "chapter_id",
    "Sentence": "paragraph_id",
}


class UnitOfWork:
    """Collects models whose state needs to be persisted and commits them
    together through the appropriate repositories."""

    def __init__(
        self,
        repos: dict[type[DockbModel], BaseRepository[Any]] | None = None,
        reconstructor: Any | None = None,
        on_commit: Any | None = None,
    ) -> None:
        self._repos = repos
        self._reconstructor = reconstructor
        self._on_commit = on_commit
        self._new: list[tuple[DockbModel, dict[str, str]]] = []
        self._changed: list[tuple[DockbModel, dict[str, str]]] = []
        self._deleted: list[tuple[DockbModel, dict[str, str]]] = []

    def register(self, model: DockbModel, **parent_ids: str) -> None:
        """Track *model* for persistence based on its DataState."""
        required = _PARENT_REQUIREMENTS.get(type(model).__name__)
        if required is not None and required not in parent_ids:
            raise ValueError(f"{type(model).__name__} requires parent_id '{required}'")
        match model.state:
            case DataState.NEW:
                self._new.append((model, parent_ids))
            case DataState.CHANGED:
                self._changed.append((model, parent_ids))
            case DataState.DELETED:
                self._deleted.append((model, parent_ids))

    def commit(
        self,
        repos: dict[type[DockbModel], BaseRepository[Any]] | None = None,
    ) -> None:
        """Strict: validate all entries, then persist. Clears lists only on success."""
        if repos is None:
            repos = self._repos
        if repos is None:
            raise ValueError("No repos available for commit")

        # Pre-validate deleted entries (strict)
        for model, _ in self._deleted:
            if model.state != DataState.DELETED:
                raise ValueError(f"{type(model).__name__} {model.id} is no longer DELETED," f" cannot delete")
            if model.dirty:
                raise ValueError(f"{type(model).__name__} {model.id} is dirty, cannot delete")

        success = False
        try:
            for model, parent_ids in self._new:
                repos[type(model)].save(model, **parent_ids)
            for model, parent_ids in self._changed:
                repos[type(model)].save(model, **parent_ids)
            for model, parent_ids in self._deleted:
                repos[type(model)].save(model, **parent_ids)
            success = True
        finally:
            if success:
                self._clear()
        if success and self._on_commit is not None:
            self._on_commit()

    def flush_pending(self) -> None:
        """Lenient: reconstruct dirty new/changed, handle deleted directly, then commit."""
        repos = self._repos
        if repos is None:
            raise ValueError("No repos available for flush")

        if self._reconstructor is not None:
            for model, _ in self._new:
                if model.dirty:
                    self._reconstructor.run(model)
            for model, _ in self._changed:
                if model.dirty:
                    self._reconstructor.run(model)

        # Handle deleted directly (lenient — skip resurrected, save even if dirty)
        for model, parent_ids in self._deleted:
            if model.state != DataState.DELETED:
                self._auto_promote(model, parent_ids)
                continue
            repos[type(model)].save(model, **parent_ids)
        self._deleted.clear()

        self.commit()

    def _auto_promote(self, model: DockbModel, parent_ids: dict[str, str]) -> None:
        """Move *model* from _deleted to the correct list based on current state."""
        target = {
            DataState.NEW: self._new,
            DataState.CHANGED: self._changed,
        }.get(model.state)
        if target is None:
            return  # _ or SYNC — just drop
        for lst in (self._new, self._changed, self._deleted):
            lst[:] = [(m, p) for m, p in lst if m is not model]
        target.append((model, parent_ids))

    def _clear(self) -> None:
        self._new.clear()
        self._changed.clear()
        self._deleted.clear()
