"""Tests for reconstructing a chapter markdown file from the graph."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from dockb.exceptions import ChapterMismatchError
from dockb.models.base import DataState
from dockb.models.chapter import Chapter
from dockb.models.paragraph import Paragraph
from dockb.models.sentence import Sentence
from dockb.models.token import Token
from dockb.repositories.chapter_repository import ChapterRepository
from dockb.services.markdown_export import reconstruct_chapter_file, reconstruct_chapter_markdown


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


def test_reconstruct_chapter_markdown_renders_loaded_chapter(nlp):
    chapter = _make_chapter("c1", _make_paragraph("p1", "Hi there."))
    rendered = reconstruct_chapter_markdown("c1", _repo(chapter), nlp)
    assert rendered == "---\nid: c1\ntitle: Chapter 1\n---\n\n" '<span data-par-id="p1">Hi there.</span>\n'


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
