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
def reader(git_repo):
    return SnapshotReader(base_dir=git_repo)


@pytest.fixture()
def writer(git_repo):
    return SnapshotWriter(base_dir=git_repo)


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


class TestListSnapshots:
    def test_empty_when_no_commits(self, reader):
        mock_chapter_repo = MagicMock()
        mock_uow_factory = MagicMock()
        svc = HistoryService(reader=reader, chapter_repo=mock_chapter_repo, uow_factory=mock_uow_factory)
        result = svc.list_snapshots("c-nonexistent")
        assert result == []

    def test_single_snapshot(self, reader, writer):
        ch = _make_chapter(ch_id="c-single", title="One")
        writer.write(ch)
        mock_chapter_repo = MagicMock()
        mock_uow_factory = MagicMock()
        svc = HistoryService(reader=reader, chapter_repo=mock_chapter_repo, uow_factory=mock_uow_factory)
        result = svc.list_snapshots("c-single")
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

        mock_chapter_repo = MagicMock()
        mock_uow_factory = MagicMock()
        svc = HistoryService(reader=reader, chapter_repo=mock_chapter_repo, uow_factory=mock_uow_factory)
        result = svc.list_snapshots("c-multi")
        assert len(result) == 2

    def test_pagination_limit(self, reader, writer):
        ch = _make_chapter(ch_id="c-page", title="T")
        writer.write(ch)
        ch.title = "V2"
        writer.write(ch)

        mock_chapter_repo = MagicMock()
        mock_uow_factory = MagicMock()
        svc = HistoryService(reader=reader, chapter_repo=mock_chapter_repo, uow_factory=mock_uow_factory)
        result = svc.list_snapshots("c-page", limit=1)
        assert len(result) == 1

    def test_pagination_offset(self, reader, writer):
        ch = _make_chapter(ch_id="c-off", title="T")
        writer.write(ch)
        ch.title = "V2"
        writer.write(ch)

        mock_chapter_repo = MagicMock()
        mock_uow_factory = MagicMock()
        svc = HistoryService(reader=reader, chapter_repo=mock_chapter_repo, uow_factory=mock_uow_factory)
        all_snaps = svc.list_snapshots("c-off")
        offset_result = svc.list_snapshots("c-off", offset=1)
        assert len(offset_result) == len(all_snaps) - 1


class TestRestore:
    def test_restore_returns_chapter(self, reader, writer):
        ch = _make_chapter(ch_id="c-restore", title="Original")
        commit_id = writer.write(ch)

        mock_chapter_repo = MagicMock()
        mock_uow_factory = MagicMock()
        svc = HistoryService(reader=reader, chapter_repo=mock_chapter_repo, uow_factory=mock_uow_factory)
        result = svc.restore("c-restore", commit_id)
        assert result is not None
        assert isinstance(result, Chapter)
        assert result.id == "c-restore"
        assert result.title == "Original"

    def test_restore_persists_chapter(self, reader, writer):
        ch = _make_chapter(ch_id="c-persist", title="Persist")
        commit_id = writer.write(ch)

        mock_chapter_repo = MagicMock()
        mock_uow = MagicMock()
        mock_uow_factory = MagicMock()
        mock_uow_factory.get_unit_of_work.return_value = mock_uow
        svc = HistoryService(reader=reader, chapter_repo=mock_chapter_repo, uow_factory=mock_uow_factory)
        svc.restore("c-persist", commit_id)
        mock_uow.register.assert_called_once()
        mock_uow.commit.assert_called_once()

    def test_restore_not_found(self, reader):
        mock_chapter_repo = MagicMock()
        mock_uow_factory = MagicMock()
        svc = HistoryService(reader=reader, chapter_repo=mock_chapter_repo, uow_factory=mock_uow_factory)
        with pytest.raises(SnapshotError):
            svc.restore("c-nonexistent", "deadbeef" * 5)

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

        mock_chapter_repo = MagicMock()
        mock_uow_factory = MagicMock()
        svc = HistoryService(reader=reader, chapter_repo=mock_chapter_repo, uow_factory=mock_uow_factory)
        result = svc.restore("c-version", commit1)
        assert result is not None
        assert result.title == "V1"
