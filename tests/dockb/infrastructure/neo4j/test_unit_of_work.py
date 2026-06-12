"""Tests for UnitOfWork."""

from unittest.mock import MagicMock

import pytest

from dockb.infrastructure.neo4j.unit_of_work import UnitOfWork
from dockb.models.base import DataState
from dockb.models.chapter import Chapter
from dockb.models.document import Document
from dockb.models.paragraph import Paragraph
from dockb.models.sentence import Sentence

# ---------------------------------------------------------------------------
# register()
# ---------------------------------------------------------------------------


class TestUnitOfWorkRegister:
    def test_registers_new_model_with_parent_ids(self):
        uow = UnitOfWork()
        model = Document()
        model.state = DataState.NEW
        uow.register(model, document_id="d1")
        assert uow._new == [(model, {"document_id": "d1"})]

    def test_registers_changed_model(self):
        uow = UnitOfWork()
        model = Document()
        model.state = DataState.CHANGED
        uow.register(model)
        assert uow._changed == [(model, {})]

    def test_registers_deleted_model(self):
        uow = UnitOfWork()
        model = Document()
        model.state = DataState.DELETED
        uow.register(model)
        assert uow._deleted == [(model, {})]

    def test_skips_sync_model(self):
        uow = UnitOfWork()
        model = Document()
        model.state = DataState.SYNC
        uow.register(model)
        assert not uow._new
        assert not uow._changed
        assert not uow._deleted

    def test_skips_nothing_model(self):
        uow = UnitOfWork()
        model = Document()
        model.state = DataState._
        uow.register(model)
        assert not uow._new
        assert not uow._changed
        assert not uow._deleted

    # ------------------------------------------------------------------
    # parent_id validation
    # ------------------------------------------------------------------

    def test_register_chapter_without_document_id_raises(self):
        uow = UnitOfWork()
        model = Chapter()
        model.state = DataState.NEW
        with pytest.raises(ValueError, match="Chapter requires parent_id 'document_id'"):
            uow.register(model)

    def test_register_chapter_with_document_id_succeeds(self):
        uow = UnitOfWork()
        model = Chapter()
        model.state = DataState.NEW
        uow.register(model, document_id="d1")
        assert uow._new == [(model, {"document_id": "d1"})]

    def test_register_paragraph_without_chapter_id_raises(self):
        uow = UnitOfWork()
        model = Paragraph()
        model.state = DataState.CHANGED
        with pytest.raises(ValueError, match="Paragraph requires parent_id 'chapter_id'"):
            uow.register(model)

    def test_register_paragraph_with_chapter_id_succeeds(self):
        uow = UnitOfWork()
        model = Paragraph()
        model.state = DataState.CHANGED
        uow.register(model, chapter_id="c1")
        assert uow._changed == [(model, {"chapter_id": "c1"})]

    def test_register_sentence_without_paragraph_id_raises(self):
        uow = UnitOfWork()
        model = Sentence()
        model.state = DataState.DELETED
        with pytest.raises(ValueError, match="Sentence requires parent_id 'paragraph_id'"):
            uow.register(model)

    def test_register_sentence_with_paragraph_id_succeeds(self):
        uow = UnitOfWork()
        model = Sentence()
        model.state = DataState.DELETED
        uow.register(model, paragraph_id="p1")
        assert uow._deleted == [(model, {"paragraph_id": "p1"})]

    def test_register_document_without_parent_ids_succeeds(self):
        uow = UnitOfWork()
        model = Document()
        model.state = DataState.NEW
        uow.register(model)
        assert uow._new == [(model, {})]

    def test_register_changed_sentence_without_paragraph_id_raises(self):
        uow = UnitOfWork()
        model = Sentence()
        model.state = DataState.CHANGED
        with pytest.raises(ValueError, match="Sentence requires parent_id 'paragraph_id'"):
            uow.register(model)

    def test_register_new_sentence_without_paragraph_id_raises(self):
        uow = UnitOfWork()
        model = Sentence()
        model.state = DataState.NEW
        with pytest.raises(ValueError, match="Sentence requires parent_id 'paragraph_id'"):
            uow.register(model)


# ---------------------------------------------------------------------------
# commit()
# ---------------------------------------------------------------------------


class TestUnitOfWorkCommit:
    def test_calls_repo_save_for_new(self):
        uow = UnitOfWork()
        model = Document()
        model.state = DataState.NEW
        repo = MagicMock()
        uow.register(model, document_id="d1")
        uow.commit({Document: repo})
        repo.save.assert_called_once_with(model, document_id="d1")

    def test_calls_repo_save_for_changed(self):
        uow = UnitOfWork()
        model = Document()
        model.state = DataState.CHANGED
        repo = MagicMock()
        uow.register(model)
        uow.commit({Document: repo})
        repo.save.assert_called_once_with(model)

    def test_calls_repo_save_for_deleted(self):
        uow = UnitOfWork()
        model = Document()
        model.state = DataState.DELETED
        repo = MagicMock()
        uow.register(model)
        uow.commit({Document: repo})
        repo.save.assert_called_once_with(model)

    def test_mixed_models_all_saved_to_correct_repos(self):
        # Separate mocks per model type verify dispatch by repos[type(model)]
        # Each model type has its own repository class (e.g. DocumentRepository, ChapterRepository)
        uow = UnitOfWork()
        doc = Document()
        doc.state = DataState.NEW
        chapter = Chapter()
        chapter.state = DataState.CHANGED
        doc_repo = MagicMock()
        ch_repo = MagicMock()
        uow.register(doc)
        uow.register(chapter, document_id="d1")
        uow.commit({Document: doc_repo, Chapter: ch_repo})
        doc_repo.save.assert_called_once_with(doc)
        ch_repo.save.assert_called_once_with(chapter, document_id="d1")

    def test_clears_lists_after_commit(self):
        uow = UnitOfWork()
        model = Document()
        model.state = DataState.NEW
        repo = MagicMock()
        uow.register(model)
        uow.commit({Document: repo})
        assert not uow._new
        assert not uow._changed
        assert not uow._deleted

    def test_does_not_clear_lists_on_failure(self):
        uow = UnitOfWork()
        model = Document()
        model.state = DataState.NEW
        repo = MagicMock()
        repo.save.side_effect = RuntimeError("fail")
        uow.register(model)
        with pytest.raises(RuntimeError):
            uow.commit({Document: repo})
        assert uow._new

    def test_commit_with_no_registered_models(self):
        uow = UnitOfWork()
        uow.commit({})

    def test_calls_repo_save_for_deleted_with_parent_ids(self):
        uow = UnitOfWork()
        model = Sentence()
        model.state = DataState.DELETED
        repo = MagicMock()
        uow.register(model, paragraph_id="p1")
        uow.commit({Sentence: repo})
        repo.save.assert_called_once_with(model, paragraph_id="p1")

    def test_commit_uses_stored_repos_when_none_passed(self):
        repo = MagicMock()
        uow = UnitOfWork(repos={Document: repo})
        model = Document()
        model.state = DataState.NEW
        uow.register(model)
        uow.commit()
        repo.save.assert_called_once_with(model)


# ---------------------------------------------------------------------------
# on_commit callback
# ---------------------------------------------------------------------------


class TestUnitOfWorkOnCommit:
    def test_calls_on_commit_after_successful_commit(self):
        on_commit = MagicMock()
        uow = UnitOfWork(on_commit=on_commit)
        model = Document()
        model.state = DataState.NEW
        repo = MagicMock()
        uow.register(model)
        uow.commit({Document: repo})
        on_commit.assert_called_once()

    def test_does_not_call_on_commit_if_save_fails(self):
        on_commit = MagicMock()
        uow = UnitOfWork(on_commit=on_commit)
        model = Document()
        model.state = DataState.NEW
        repo = MagicMock()
        repo.save.side_effect = RuntimeError("fail")
        uow.register(model)
        with pytest.raises(RuntimeError):
            uow.commit({Document: repo})
        on_commit.assert_not_called()

    def test_on_commit_is_idempotent_when_called_twice(self):
        on_commit = MagicMock()
        uow = UnitOfWork(on_commit=on_commit)
        model = Document()
        model.state = DataState.NEW
        repo = MagicMock()
        uow.register(model)
        uow.commit({Document: repo, Chapter: repo})
        on_commit.assert_called_once()


# ---------------------------------------------------------------------------
# flush_pending()
# ---------------------------------------------------------------------------


class TestUnitOfWorkFlushPending:
    def test_reconstructs_dirty_new_models(self):
        reconstructor = MagicMock()
        uow = UnitOfWork(reconstructor=reconstructor, repos={Document: MagicMock()})
        model = Document()
        model.state = DataState.NEW
        model.dirty = True
        uow.register(model)
        uow.flush_pending()
        reconstructor.run.assert_called_once_with(model)

    def test_reconstructs_dirty_changed_models(self):
        reconstructor = MagicMock()
        uow = UnitOfWork(reconstructor=reconstructor, repos={Document: MagicMock()})
        model = Document()
        model.state = DataState.CHANGED
        model.dirty = True
        uow.register(model)
        uow.flush_pending()
        reconstructor.run.assert_called_once_with(model)

    def test_does_not_reconstruct_dirty_deleted_models(self):
        reconstructor = MagicMock()
        repo = MagicMock()
        uow = UnitOfWork(reconstructor=reconstructor, repos={Document: repo})
        model = Document()
        model.state = DataState.DELETED
        uow.register(model)
        model.dirty = True
        uow.flush_pending()
        reconstructor.run.assert_not_called()
        repo.save.assert_called_once_with(model)

    def test_skips_non_dirty_models(self):
        reconstructor = MagicMock()
        uow = UnitOfWork(reconstructor=reconstructor, repos={Document: MagicMock()})
        clean = Document()
        clean.state = DataState.NEW
        clean.dirty = False
        dirty = Document()
        dirty.state = DataState.NEW
        dirty.dirty = True
        uow.register(clean)
        uow.register(dirty)
        uow.flush_pending()
        assert reconstructor.run.call_count == 1

    def test_commits_after_reconstruction(self):
        reconstructor = MagicMock()
        repo = MagicMock()
        uow = UnitOfWork(reconstructor=reconstructor, repos={Document: repo})
        model = Document()
        model.state = DataState.NEW
        model.dirty = True
        uow.register(model)
        uow.flush_pending()
        repo.save.assert_called_once()

    def test_clears_lists_after_flush(self):
        reconstructor = MagicMock()
        uow = UnitOfWork(reconstructor=reconstructor, repos={Document: MagicMock()})
        model = Document()
        model.state = DataState.NEW
        model.dirty = True
        uow.register(model)
        uow.flush_pending()
        assert not uow._new
        assert not uow._changed
        assert not uow._deleted

    def test_flush_without_reconstructor_still_commits(self):
        uow = UnitOfWork(repos={Document: MagicMock()})
        model = Document()
        model.state = DataState.NEW
        model.dirty = False
        uow.register(model)
        uow.flush_pending()
        assert not uow._new

    def test_flush_without_repos_raises(self):
        uow = UnitOfWork(reconstructor=MagicMock())
        model = Document()
        model.state = DataState.NEW
        model.dirty = True
        uow.register(model)
        with pytest.raises(ValueError, match="No repos"):
            uow.flush_pending()

    def test_deleted_dirty_commit_fails_then_flush_succeeds(self):
        repo = MagicMock()
        on_commit = MagicMock()
        reconstructor = MagicMock()
        uow = UnitOfWork(
            repos={Document: repo},
            reconstructor=reconstructor,
            on_commit=on_commit,
        )
        model = Document()
        model.state = DataState.DELETED
        uow.register(model)
        model.dirty = True
        with pytest.raises(ValueError, match="dirty"):
            uow.commit()
        on_commit.assert_not_called()
        reconstructor.run.assert_not_called()
        repo.save.assert_not_called()
        uow.flush_pending()
        reconstructor.run.assert_not_called()
        repo.save.assert_called_once_with(model)

    def test_deleted_dirty_and_changed_commit_fails_then_flush_succeeds(self):
        repo = MagicMock()
        on_commit = MagicMock()
        reconstructor = MagicMock()
        reconstructor.run.side_effect = lambda m: setattr(m, "dirty", False)
        uow = UnitOfWork(
            repos={Document: repo},
            reconstructor=reconstructor,
            on_commit=on_commit,
        )
        model = Document()
        model.state = DataState.DELETED
        uow.register(model)
        model.dirty = True
        model.state = DataState.CHANGED
        uow.register(model)
        assert uow._changed == [(model, {})]
        assert uow._deleted == [(model, {})]
        with pytest.raises(ValueError, match="DELETED"):
            uow.commit()
        on_commit.assert_not_called()
        reconstructor.run.assert_not_called()
        repo.save.assert_not_called()
        save_states: list[tuple[object, bool]] = []
        repo.save.side_effect = lambda m, **kw: save_states.append((m.state, m.dirty))
        uow.flush_pending()
        reconstructor.run.assert_called_once_with(model)
        assert save_states == [(DataState.CHANGED, False)]  # updated, not deleted


class TestUnitOfWorkCommitFlushWithDeleted:
    """Integration tests: commit() strict validation + flush_pending() lenient recovery."""

    def test_commit_fails_then_flush_deletes_dirty_deleted(self):
        repo = MagicMock()
        on_commit = MagicMock()
        reconstructor = MagicMock()
        uow = UnitOfWork(
            repos={Document: repo},
            reconstructor=reconstructor,
            on_commit=on_commit,
        )
        model = Document()
        model.state = model.state  # (shut up linter)
        model.state = DataState.DELETED
        model.dirty = False
        uow.register(model)
        # Simulate concurrent edit that dirties the model after registration
        model.dirty = True
        # commit() is strict — raises on dirty DELETED
        with pytest.raises(ValueError, match="dirty"):
            uow.commit()
        # Lists survive the failed commit so flush_pending() can recover
        assert uow._deleted
        # flush_pending() is lenient — deletes even when dirty
        uow.flush_pending()
        repo.save.assert_called_once_with(model)

    def test_commit_fails_then_flush_updates_resurrected_deleted(self):
        repo = MagicMock()
        on_commit = MagicMock()
        reconstructor = MagicMock()
        uow = UnitOfWork(
            repos={Document: repo},
            reconstructor=reconstructor,
            on_commit=on_commit,
        )
        model = Document()
        model.state = DataState.DELETED
        model.dirty = False
        uow.register(model)
        # Simulate resurrection + subsequent edit
        model.dirty = True
        model.state = DataState.CHANGED
        uow.register(model)  # re-register with new state
        # commit() is strict — stale _deleted entry fails validation
        with pytest.raises(ValueError, match="no longer DELETED"):
            uow.commit()
        # flush_pending() auto-promotes resurrected model and commits
        uow.flush_pending()
        # Model should have been updated, not deleted
        assert repo.save.call_count == 1
        repo.save.assert_called_once_with(model)
