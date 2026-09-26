"""Tests for reconstructing a chapter markdown file from the graph."""

from __future__ import annotations

import subprocess
from unittest.mock import MagicMock

import pytest

from dockb.exceptions import ChapterMismatchError
from dockb.infrastructure.document_store import DocumentStore
from dockb.models.base import DataState
from dockb.models.chapter import Chapter
from dockb.models.document import Document
from dockb.models.paragraph import Paragraph
from dockb.models.sentence import Sentence
from dockb.models.token import Token
from dockb.repositories.chapter_repository import ChapterRepository
from dockb.repositories.document_repository import DocumentRepository
from dockb.services.markdown_export import (
    reconstruct_chapter_file,
    reconstruct_chapter_markdown,
    reconstruct_chapter_to_store,
)


def _make_paragraph(par_id: str, *sentence_texts: str) -> Paragraph:
    paragraph = Paragraph(id=par_id, state=DataState.SYNC)
    for text in sentence_texts:
        sentence = Sentence(state=DataState.SYNC)
        token = Token(text=text, state=DataState.SYNC)
        sentence.tokens.append(token)
        paragraph.sentences.append(sentence)
    return paragraph


def _make_chapter(ch_id: str, *paragraphs: Paragraph, title: str = "Chapter 1") -> Chapter:
    chapter = Chapter(id=ch_id, title=title, state=DataState.SYNC)
    for paragraph in paragraphs:
        chapter.paragraphs.append(paragraph)
    return chapter


def _repo(chapter: Chapter | None) -> MagicMock:
    repo = MagicMock(spec=ChapterRepository)
    repo.load.return_value = chapter
    return repo


def _doc_repo(document: Document | None) -> MagicMock:
    repo = MagicMock(spec=DocumentRepository)
    repo.load.return_value = document
    return repo


def _git_store(tmp_path) -> DocumentStore:
    subprocess.run(["git", "init"], cwd=str(tmp_path), check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=str(tmp_path), check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=str(tmp_path), check=True, capture_output=True)
    return DocumentStore(base_dir=tmp_path)


def test_reconstruct_chapter_markdown_renders_loaded_chapter(nlp):
    chapter = _make_chapter("c1", _make_paragraph("p1", "Hi there."))
    rendered = reconstruct_chapter_markdown("c1", _repo(chapter), nlp)
    assert rendered == "---\nid: c1\ntitle: Chapter 1\n---\n\n" '<span data-par-id="p1">\nHi there.\n</span>\n'


def test_reconstruct_chapter_markdown_includes_title_only_for_unknown_attrs(nlp):
    chapter = _make_chapter("c2", title="Renamed")
    rendered = reconstruct_chapter_markdown("c2", _repo(chapter), nlp)
    assert rendered.startswith("---\nid: c2\ntitle: Renamed\n---\n")


def test_reconstruct_chapter_markdown_raises_for_unknown_chapter(nlp):
    with pytest.raises(ChapterMismatchError):
        reconstruct_chapter_markdown("missing", _repo(None), nlp)


def test_reconstruct_chapter_file_writes_rendered_content(nlp, tmp_path):
    chapter = _make_chapter("c1", _make_paragraph("p1", "Hi there."))
    target = tmp_path / "chapter.md"
    reconstruct_chapter_file("c1", _repo(chapter), target, nlp)
    assert target.read_text() == reconstruct_chapter_markdown("c1", _repo(chapter), nlp)


def test_reconstruct_chapter_file_raises_for_unknown_chapter(nlp, tmp_path):
    target = tmp_path / "chapter.md"
    with pytest.raises(ChapterMismatchError):
        reconstruct_chapter_file("missing", _repo(None), target, nlp)
    assert not target.exists()


def test_reconstruct_to_store_writes_title_act_layout_and_commits(nlp, tmp_path):
    chapter = _make_chapter("c1", _make_paragraph("p1", "Hi there."), title="Intro")
    chapter.act = "Act I"
    chapter_repo = _repo(chapter)
    chapter_repo.find_document_id.return_value = "d1"
    document = Document(id="d1", title="Faith", state=DataState.SYNC)
    store = _git_store(tmp_path)

    path = reconstruct_chapter_to_store("c1", chapter_repo, _doc_repo(document), store, nlp)

    assert path == store.chapter_file("Faith", "Act I", "Intro")
    assert path.read_text() == reconstruct_chapter_markdown("c1", _repo(chapter), nlp)
    log = subprocess.run(["git", "log", "--format=%H"], cwd=str(tmp_path), capture_output=True, text=True, check=False)
    assert log.returncode == 0
    assert log.stdout.strip()


def test_reconstruct_to_store_puts_empty_act_under_act_none(nlp, tmp_path):
    chapter = _make_chapter("c1", _make_paragraph("p1", "Hi there."), title="Intro")
    chapter_repo = _repo(chapter)
    chapter_repo.find_document_id.return_value = "d1"
    document = Document(id="d1", title="Faith", state=DataState.SYNC)
    store = _git_store(tmp_path)

    path = reconstruct_chapter_to_store("c1", chapter_repo, _doc_repo(document), store, nlp)

    assert path == store.chapter_file("Faith", "", "Intro")
    assert path.is_file()


def test_reconstruct_to_store_raises_for_orphan_chapter(nlp, tmp_path):
    chapter = _make_chapter("c1", _make_paragraph("p1", "Hi there."), title="Intro")
    chapter_repo = _repo(chapter)
    chapter_repo.find_document_id.return_value = None
    store = _git_store(tmp_path)

    with pytest.raises(ChapterMismatchError, match="no owning document"):
        reconstruct_chapter_to_store("c1", chapter_repo, _doc_repo(None), store, nlp)

    assert not store.document_dir("Faith").exists()


def test_reconstruct_to_store_raises_for_unknown_chapter(nlp, tmp_path):
    store = _git_store(tmp_path)
    with pytest.raises(ChapterMismatchError, match="not found"):
        reconstruct_chapter_to_store("missing", _repo(None), _doc_repo(Document(id="d1")), store, nlp)
