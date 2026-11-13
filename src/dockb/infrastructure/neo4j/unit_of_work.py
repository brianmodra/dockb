"""Unit of Work — tracks models to persist and dispatches them to repositories."""

from typing import Any

from dockb.infrastructure.neo4j.base import BaseRepository
from dockb.infrastructure.neo4j.serialized_session import SessionLike
from dockb.models.base import DataState, DockbModel

# Model type name → required parent_id key for Cypher relationship matching.
# Document is top-level and needs no parent.
_PARENT_REQUIREMENTS: dict[str, str] = {
    "Chapter": "document_id",
    "Paragraph": "chapter_id",
    "Sentence": "paragraph_id",
}


def session_from_repos(repos: dict[type[DockbModel], Any]) -> SessionLike | None:
    """Return the shared session a set of repositories runs through, if any.

    The unit of work commits through one transaction on this session. Production
    repositories are the concrete subclasses that expose it; a test double has none,
    and its saves then run directly.
    """
    for repo in repos.values():
        if isinstance(repo, BaseRepository):
            return repo.session
    return None


class UnitOfWork:
    """Collects models whose state needs to be persisted and commits them
    together through the appropriate repositories."""

    def __init__(
        self,
        repos: dict[type[DockbModel], BaseRepository[Any]] | None = None,
        reconstructor: Any | None = None,
        on_commit: Any | None = None,
        session: SessionLike | None = None,
    ) -> None:
        self._repos = repos
        self._reconstructor = reconstructor
        self._on_commit = on_commit
        self._session = session
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

        self._persist(repos, lenient=False)

    def _persist(self, repos: dict[type[DockbModel], BaseRepository[Any]], *, lenient: bool) -> None:
        """Write every registered batch inside one transaction, then commit it.

        The transaction *is* the commit: all ``save_many`` calls run through it, so
        the managed context commits on a clean exit or rolls the whole set back when
        any write raises. The tracking lists clear only once the transaction commits.
        """
        session = self._session if self._session is not None else session_from_repos(repos)
        success = False
        try:
            if session is None:
                self._write(repos, session=None, lenient=lenient)
            else:
                with session.begin_transaction() as tx:
                    self._write(repos, session=tx, lenient=lenient)
            success = True
        finally:
            if success:
                self._clear()
        if success and self._on_commit is not None:
            self._on_commit()

    def _write(
        self,
        repos: dict[type[DockbModel], BaseRepository[Any]],
        *,
        session: SessionLike | None,
        lenient: bool,
    ) -> None:
        """Issue every batch's writes in registration order, through *session*.

        Strict commits batch deletions through ``save_many`` like any other state.
        Lenient flushes write deletions one at a time so a dirty model can still be
        removed (deletion is unconditional)."""
        for entries in (self._new, self._changed):
            for model_type, group in self._group_by_type(entries):
                self._save_many(repos[model_type], group, session)
        if lenient:
            for model, parent_ids in self._deleted:
                self._save(repos[type(model)], model, parent_ids, session)
        else:
            for model_type, group in self._group_by_type(self._deleted):
                self._save_many(repos[model_type], group, session)

    @staticmethod
    def _save_many(repo: BaseRepository[Any], group: list[tuple[DockbModel, dict[str, str]]], session: SessionLike | None) -> None:
        """Persist *group*; omit the session keyword when there is none to pass."""
        if session is None:
            repo.save_many(group)
        else:
            repo.save_many(group, session=session)

    @staticmethod
    def _save(repo: BaseRepository[Any], model: DockbModel, parent_ids: dict[str, str], session: SessionLike | None) -> None:
        """Persist one *model*; omit the session keyword when there is none to pass."""
        params: dict[str, Any] = dict(parent_ids)
        if session is not None:
            params["session"] = session
        repo.save(model, **params)

    @staticmethod
    def _group_by_type(
        entries: list[tuple[DockbModel, dict[str, str]]],
    ) -> list[tuple[type[DockbModel], list[tuple[DockbModel, dict[str, str]]]]]:
        """Partition *entries* by model type, preserving first-appearance order.

        Registration is parent-first (chapter, then its paragraphs, then their
        sentences), so grouping keeps the write order each repository's Cypher
        depends on while letting each repository persist its set in one batch."""
        groups: dict[type[DockbModel], list[tuple[DockbModel, dict[str, str]]]] = {}
        order: list[type[DockbModel]] = []
        for model, parent_ids in entries:
            model_type = type(model)
            if model_type not in groups:
                groups[model_type] = []
                order.append(model_type)
            groups[model_type].append((model, parent_ids))
        return [(model_type, groups[model_type]) for model_type in order]

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

        # Lenient — skip resurrected, keep the rest to delete in the same transaction.
        surviving: list[tuple[DockbModel, dict[str, str]]] = []
        for model, parent_ids in self._deleted:
            if model.state != DataState.DELETED:
                self._auto_promote(model, parent_ids)
                continue
            surviving.append((model, parent_ids))
        self._deleted.clear()
        self._deleted.extend(surviving)

        self._persist(repos, lenient=True)

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
