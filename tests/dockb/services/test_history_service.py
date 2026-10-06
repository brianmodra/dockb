"""Tests for HistoryService — snapshot listing and chapter restoration."""

from __future__ import annotations

import subprocess
from unittest.mock import MagicMock

import pytest

from dockb.exceptions import SnapshotError
from dockb.infrastructure.history.snapshot_reader import SnapshotReader
from dockb.infrastructure.history.snapshot_writer import SnapshotWriter
from dockb.models.base import DataState
from dockb.models.chapter import Chapter
from dockb.models.paragraph import Paragraph
from dockb.models.sentence import Sentence
from dockb.models.token import Token
from dockb.services.history_service import HistoryService


@pytest.fixture()
def git_repo(tmp_path):
    """Create a temporary git repository."""
    subprocess.run(["git", "init"], cwd=str(tmp_path), check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=str(tmp_path), check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=str(tmp_path), check=True, capture_output=True)
    return tmp_path


@pytest.fixture()
def reader(git_repo, nlp):
    return SnapshotReader(base_dir=git_repo, nlp=nlp)


@pytest.fixture()
def writer(git_repo, nlp):
    return SnapshotWriter(base_dir=git_repo, nlp=nlp)


def _make_chapter(ch_id: str = "c1", title: str = "Ch1", text: str = "Hello.") -> Chapter:
    ch = Chapter(id=ch_id, title=title, state=DataState.SYNC)
    token = Token()
    token.set_text(text)
    sentence = Sentence()
    sentence.tokens.append(token)
    paragraph = Paragraph()
    paragraph.sentences.append(sentence)
    ch.paragraphs.append(paragraph)
    return ch


_OWNER = "acct-1"
_OTHER = "acct-2"


def _owned_chapter_repo(document_id: str = "d1") -> MagicMock:
    """A chapter repository where every chapter belongs to the account under test.

    The real repository answers this by walking to the document above the chapter, so
    the stub answers by account alone; what these tests are about is whether the service
    asks at all, and with whose account.
    """
    repo = MagicMock()
    repo.find_document_id.side_effect = lambda node_id, owner: document_id if owner == _OWNER else None
    return repo


class TestListSnapshots:
    def test_empty_when_no_commits(self, reader):
        mock_chapter_repo = _owned_chapter_repo()
        mock_uow_factory = MagicMock()
        svc = HistoryService(reader=reader, chapter_repo=mock_chapter_repo, uow_factory=mock_uow_factory)
        result = svc.list_snapshots("c-nonexistent", owner=_OWNER)
        assert result == []

    def test_single_snapshot(self, reader, writer):
        ch = _make_chapter(ch_id="c-single", title="One")
        writer.write(ch)
        mock_chapter_repo = _owned_chapter_repo()
        mock_uow_factory = MagicMock()
        svc = HistoryService(reader=reader, chapter_repo=mock_chapter_repo, uow_factory=mock_uow_factory)
        result = svc.list_snapshots("c-single", owner=_OWNER)
        assert len(result) == 1
        assert "commit_id" in result[0]
        assert "datetime" in result[0]

    def test_multiple_snapshots_reverse_chronological(self, reader, writer):
        ch = _make_chapter(ch_id="c-multi", title="V1")
        writer.write(ch)
        ch.title = "V2"
        ch.paragraphs.clear()
        token = Token()
        token.set_text("V2 text.")
        sentence = Sentence()
        sentence.tokens.append(token)
        ch.paragraphs.append(Paragraph())
        ch.paragraphs[0].sentences.append(sentence)
        writer.write(ch)

        mock_chapter_repo = _owned_chapter_repo()
        mock_uow_factory = MagicMock()
        svc = HistoryService(reader=reader, chapter_repo=mock_chapter_repo, uow_factory=mock_uow_factory)
        result = svc.list_snapshots("c-multi", owner=_OWNER)
        assert len(result) == 2

    def test_pagination_limit(self, reader, writer):
        ch = _make_chapter(ch_id="c-page", title="T")
        writer.write(ch)
        ch.title = "V2"
        writer.write(ch)

        mock_chapter_repo = _owned_chapter_repo()
        mock_uow_factory = MagicMock()
        svc = HistoryService(reader=reader, chapter_repo=mock_chapter_repo, uow_factory=mock_uow_factory)
        result = svc.list_snapshots("c-page", owner=_OWNER, limit=1)
        assert len(result) == 1

    def test_pagination_offset(self, reader, writer):
        ch = _make_chapter(ch_id="c-off", title="T")
        writer.write(ch)
        ch.title = "V2"
        writer.write(ch)

        mock_chapter_repo = _owned_chapter_repo()
        mock_uow_factory = MagicMock()
        svc = HistoryService(reader=reader, chapter_repo=mock_chapter_repo, uow_factory=mock_uow_factory)
        all_snaps = svc.list_snapshots("c-off", owner=_OWNER)
        offset_result = svc.list_snapshots("c-off", owner=_OWNER, offset=1)
        assert len(offset_result) == len(all_snaps) - 1


class TestRestore:
    def test_restore_returns_chapter(self, reader, writer):
        ch = _make_chapter(ch_id="c-restore", title="Original")
        commit_id = writer.write(ch)

        mock_chapter_repo = _owned_chapter_repo()
        mock_uow_factory = MagicMock()
        svc = HistoryService(reader=reader, chapter_repo=mock_chapter_repo, uow_factory=mock_uow_factory)
        result = svc.restore("c-restore", commit_id, owner=_OWNER)
        assert result is not None
        assert isinstance(result, Chapter)
        assert result.id == "c-restore"
        assert result.title == "Original"

    def test_restore_persists_chapter(self, reader, writer):
        ch = _make_chapter(ch_id="c-persist", title="Persist")
        commit_id = writer.write(ch)

        mock_chapter_repo = _owned_chapter_repo()
        mock_uow = MagicMock()
        mock_uow_factory = MagicMock()
        mock_uow_factory.get_unit_of_work.return_value = mock_uow
        svc = HistoryService(reader=reader, chapter_repo=mock_chapter_repo, uow_factory=mock_uow_factory)
        svc.restore("c-persist", commit_id, owner=_OWNER)
        mock_uow.register.assert_called_once()
        mock_uow.commit.assert_called_once()

    def test_restore_not_found(self, reader):
        mock_chapter_repo = _owned_chapter_repo()
        mock_uow_factory = MagicMock()
        svc = HistoryService(reader=reader, chapter_repo=mock_chapter_repo, uow_factory=mock_uow_factory)
        with pytest.raises(SnapshotError):
            svc.restore("c-nonexistent", "deadbeef" * 5, owner=_OWNER)

    def test_restore_at_specific_version(self, reader, writer):
        ch = _make_chapter(ch_id="c-version", title="V1")
        commit1 = writer.write(ch)

        ch.title = "V2"
        ch.paragraphs.clear()
        token = Token()
        token.set_text("V2.")
        sentence = Sentence()
        sentence.tokens.append(token)
        ch.paragraphs.append(Paragraph())
        ch.paragraphs[0].sentences.append(sentence)
        writer.write(ch)

        mock_chapter_repo = _owned_chapter_repo()
        mock_uow_factory = MagicMock()
        svc = HistoryService(reader=reader, chapter_repo=mock_chapter_repo, uow_factory=mock_uow_factory)
        result = svc.restore("c-version", commit1, owner=_OWNER)
        assert result is not None
        assert result.title == "V1"


class TestOwnership:
    """Snapshots live in one repository shared by every account, so the chapter they
    describe has to be claimed before its history is read or written.

    Snapshots are keyed by chapter id alone, which is not an account boundary: any
    authenticated caller who learns a chapter id would otherwise read that chapter's
    history and restore it into their own graph.
    """

    def test_list_hides_another_accounts_chapter(self, reader, writer):
        chapter = _make_chapter(ch_id="c-secret", title="Secret")
        writer.write(chapter)
        repo = _owned_chapter_repo()

        svc = HistoryService(reader=reader, chapter_repo=repo, uow_factory=MagicMock())

        assert svc.list_snapshots("c-secret", owner=_OTHER) == []

    def test_list_never_reaches_the_shared_repository_for_a_foreign_chapter(self):
        shared_reader = MagicMock()
        svc = HistoryService(reader=shared_reader, chapter_repo=_owned_chapter_repo(), uow_factory=MagicMock())

        svc.list_snapshots("c-secret", owner=_OTHER)

        shared_reader.list_commits.assert_not_called()

    def test_restore_refuses_another_accounts_chapter(self, reader, writer):
        chapter = _make_chapter(ch_id="c-secret", title="Secret")
        commit_id = writer.write(chapter)
        repo = _owned_chapter_repo()
        uow = MagicMock()
        uow_factory = MagicMock()
        uow_factory.get_unit_of_work.return_value = uow

        svc = HistoryService(reader=reader, chapter_repo=repo, uow_factory=uow_factory)

        assert svc.restore("c-secret", commit_id, owner=_OTHER) is None
        uow.register.assert_not_called()

    def test_restore_writes_the_chapter_back_under_the_document_that_owns_it(self, reader, writer):
        chapter = _make_chapter(ch_id="c-owned", title="Owned")
        commit_id = writer.write(chapter)
        repo = _owned_chapter_repo("d-owning")
        uow = MagicMock()
        uow_factory = MagicMock()
        uow_factory.get_unit_of_work.return_value = uow

        svc = HistoryService(reader=reader, chapter_repo=repo, uow_factory=uow_factory)
        svc.restore("c-owned", commit_id, owner=_OWNER)

        uow.register.assert_called_once()
        registered_chapter = uow.register.call_args.args[0]
        assert uow.register.call_args.kwargs == {"document_id": "d-owning", "owner": _OWNER}
        assert registered_chapter.state == DataState.NEW

    def test_every_lookup_carries_the_calling_account(self, reader):
        repo = _owned_chapter_repo()
        svc = HistoryService(reader=reader, chapter_repo=repo, uow_factory=MagicMock())

        svc.list_snapshots("c1", owner=_OWNER)

        assert repo.find_document_id.call_args.args == ("c1", _OWNER)
