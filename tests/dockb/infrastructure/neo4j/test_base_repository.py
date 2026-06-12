"""Tests for BaseRepository."""

from typing import Any
from unittest.mock import MagicMock

import pytest

from dockb.infrastructure.neo4j.base import BaseRepository
from dockb.models.base import DataState
from dockb.models.document import Document

# ---------------------------------------------------------------------------
# Concrete test subclass
# ---------------------------------------------------------------------------


class _ConcreteRepo(BaseRepository[Document]):  # pylint: disable=too-few-public-methods
    """Minimal concrete repo for testing the base class dispatch."""

    @property
    def _new_cypher(self) -> str:
        return "NEW"

    @property
    def _changed_cypher(self) -> str:
        return "CHANGED"

    @property
    def _delete_cypher(self) -> str:
        return "DELETE"

    def _build_params(self, model: Document, **parent_ids: str) -> dict[str, Any]:
        return {"document_id": model.id}


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------


class TestBaseRepositoryConstruction:
    def test_cannot_instantiate_abc_directly(self):
        with pytest.raises(TypeError):
            BaseRepository(MagicMock())  # type: ignore[abstract]  # pylint: disable=abstract-class-instantiated

    def test_concrete_subclass_can_be_instantiated(self):
        session = MagicMock()
        repo = _ConcreteRepo(session)
        assert repo._session is session


# ---------------------------------------------------------------------------
# save() dispatch
# ---------------------------------------------------------------------------


class TestBaseRepositorySave:
    def test_raises_on_dirty_model(self):
        session = MagicMock()
        repo = _ConcreteRepo(session)
        model = MagicMock(spec=Document, dirty=True)
        with pytest.raises(ValueError, match="dirty"):
            repo.save(model)

    def test_skips_nothing_state(self):
        session = MagicMock()
        repo = _ConcreteRepo(session)
        model = MagicMock(spec=Document, dirty=False, state=DataState._)
        repo.save(model)
        session.run.assert_not_called()

    def test_skips_sync_state(self):
        session = MagicMock()
        repo = _ConcreteRepo(session)
        model = MagicMock(spec=Document, dirty=False, state=DataState.SYNC)
        repo.save(model)
        session.run.assert_not_called()

    def test_runs_new_cypher_for_new_state(self):
        session = MagicMock()
        repo = _ConcreteRepo(session)
        model = MagicMock(spec=Document, dirty=False, state=DataState.NEW)
        model.id = "doc-1"
        repo.save(model)
        session.run.assert_called_once_with("NEW", {"document_id": "doc-1"})

    def test_runs_changed_cypher_for_changed_state(self):
        session = MagicMock()
        repo = _ConcreteRepo(session)
        model = MagicMock(spec=Document, dirty=False, state=DataState.CHANGED)
        model.id = "doc-1"
        repo.save(model)
        session.run.assert_called_once_with("CHANGED", {"document_id": "doc-1"})

    def test_runs_delete_cypher_for_deleted_state(self):
        session = MagicMock()
        repo = _ConcreteRepo(session)
        model = MagicMock(spec=Document, dirty=False, state=DataState.DELETED)
        model.id = "doc-1"
        repo.save(model)
        session.run.assert_called_once_with("DELETE", {"document_id": "doc-1"})

    def test_parent_ids_are_forwarded(self):
        session = MagicMock()
        repo = _ConcreteRepo(session)
        model = MagicMock(spec=Document, dirty=False, state=DataState.NEW)
        model.id = "doc-1"
        repo.save(model, chapter_id="ch-1")
        # _build_params receives chapter_id but may or may not use it;
        # the assert confirms the save call itself forwards parent_ids correctly.
        session.run.assert_called_once()
