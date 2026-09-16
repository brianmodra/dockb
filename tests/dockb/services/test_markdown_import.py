"""Tests for apply_chapter_file — the per-chapter-file markdown import caller."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from dockb.exceptions import ChapterMismatchError
from dockb.models.base import DataState
from dockb.models.chapter import Chapter
from dockb.models.document import Document
from dockb.models.paragraph import Paragraph
from dockb.models.sentence import Sentence
from dockb.models.token import Token
from dockb.repositories.chapter_repository import ChapterRepository
from dockb.services.markdown_import import ChapterImportSummary, apply_chapter_file


def _make_paragraph(par_id: str, *sentence_texts: str) -> Paragraph:
    paragraph = Paragraph(id=par_id, state=DataState.SYNC)
    for text in sentence_texts:
        sentence = Sentence(state=DataState.SYNC)
        token = Token(text=text, state=DataState.SYNC)
        sentence.tokens.append(token)
        paragraph.sentences.append(sentence)
    return paragraph


def _make_chapter(ch_id: str, *paragraphs: Paragraph, title: str = "Old Title") -> Chapter:
    chapter = Chapter(id=ch_id, title=title, state=DataState.SYNC)
    for paragraph in paragraphs:
        chapter.paragraphs.append(paragraph)
    return chapter


def _make_document(doc_id: str, *chapters: Chapter) -> Document:
    document = Document(id=doc_id, state=DataState.SYNC)
    for chapter in chapters:
        document.append_child(chapter)
    return document


@pytest.fixture()
def header():
    return "---\nid: c1\n---\n"


def _setup(chapter: Chapter | None) -> tuple[MagicMock, MagicMock]:
    chapter_repo = MagicMock(spec=ChapterRepository)
    chapter_repo.load.return_value = chapter
    uow_factory = MagicMock()
    return chapter_repo, uow_factory


def _register_calls(uow):
    return [(call.args[0], call.kwargs) for call in uow.register.call_args_list]


def _saved_chapter(uow):
    for model, kwargs in _register_calls(uow):
        if isinstance(model, Chapter):
            return model, kwargs
    raise AssertionError("no chapter registered")


def _saved_paragraphs(uow):
    return [(model, kwargs) for model, kwargs in _register_calls(uow) if isinstance(model, Paragraph)]


class TestNewChapter:
    def test_new_file_without_front_matter_creates_chapter(self, nlp, tmp_path):
        file = tmp_path / "Chapter 1.md"
        file.write_text("Para one sentence.\n\nPara two sentence.")
        document = _make_document("d1")
        chapter_repo, uow_factory = _setup(None)
        uow = MagicMock()
        uow_factory.get_unit_of_work.return_value = uow

        summary = apply_chapter_file(document, file, nlp, chapter_repo, uow_factory)

        assert isinstance(summary, ChapterImportSummary)
        assert summary.created is True
        assert summary.added == 2
        assert summary.changed == 0
        assert summary.deleted == 0

        chapter, kwargs = _saved_chapter(uow)
        assert chapter.state is DataState.NEW
        assert kwargs == {"document_id": "d1"}
        assert chapter.title == "Chapter 1"
        assert [p.sentences[0].get_text() for p in chapter.paragraphs] == [
            "Para one sentence.",
            "Para two sentence.",
        ]
        paragraphs = [m for m, kw in _saved_paragraphs(uow)]
        assert len(paragraphs) == 2
        assert all(p.state is DataState.NEW for p in paragraphs)
        assert all(kw == {"chapter_id": chapter.id} for _, kw in _saved_paragraphs(uow))
        assert summary.chapter_id == chapter.id
        uow.commit.assert_called_once()

    def test_new_file_with_front_matter_id_is_rejected(self, nlp, tmp_path, header):
        file = tmp_path / "orphan.md"
        file.write_text(f"{header}\n\nBody.")
        document = _make_document("d1")
        chapter_repo, uow_factory = _setup(None)

        with pytest.raises(ChapterMismatchError, match="not a child of document"):
            apply_chapter_file(document, file, nlp, chapter_repo, uow_factory)

        uow_factory.get_unit_of_work.assert_not_called()

    def test_new_chapter_takes_front_matter_title(self, nlp, tmp_path):
        file = tmp_path / "Chapter 1.md"
        file.write_text("---\ntitle: Front Title\n---\n\nBody.")
        document = _make_document("d1")
        chapter_repo, uow_factory = _setup(None)
        uow = MagicMock()
        uow_factory.get_unit_of_work.return_value = uow

        apply_chapter_file(document, file, nlp, chapter_repo, uow_factory)

        chapter, _ = _saved_chapter(uow)
        assert chapter.title == "Front Title"


class TestExistingChapter:
    def test_chapter_from_another_document_is_rejected(self, nlp, tmp_path, header):
        file = tmp_path / "c1.md"
        file.write_text(f"{header}\n\nBody.")
        other = _make_chapter("cOther", _make_paragraph("p1", "Body."))
        document = _make_document("d1", other)
        chapter_repo, uow_factory = _setup(_make_chapter("c1", _make_paragraph("p1", "Body.")))

        with pytest.raises(ChapterMismatchError, match="not a child of document"):
            apply_chapter_file(document, file, nlp, chapter_repo, uow_factory)

        uow_factory.get_unit_of_work.assert_not_called()

    def test_unmodified_file_persists_nothing(self, nlp, tmp_path, header):
        file = tmp_path / "c1.md"
        file.write_text(f'{header}\n\n<span data-par-id="p1">Only.</span>')
        loaded = _make_chapter("c1", _make_paragraph("p1", "Only."))
        document = _make_document("d1", _make_chapter("c1", _make_paragraph("p1", "Only.")))
        chapter_repo, uow_factory = _setup(loaded)
        uow = MagicMock()
        uow_factory.get_unit_of_work.return_value = uow

        summary = apply_chapter_file(document, file, nlp, chapter_repo, uow_factory)

        assert summary.created is False
        assert summary.added == summary.changed == summary.deleted == 0
        uow.register.assert_not_called()
        uow.commit.assert_not_called()

    def test_title_is_not_rewritten_for_existing_chapter(self, nlp, tmp_path, header):
        file = tmp_path / "c1.md"
        file.write_text(f"{header}\n\nNew text.")
        loaded = _make_chapter("c1", _make_paragraph("p1", "Old text."))
        document = _make_document("d1", _make_chapter("c1", _make_paragraph("p1", "Old text.")))
        chapter_repo, uow_factory = _setup(loaded)
        uow = MagicMock()
        uow_factory.get_unit_of_work.return_value = uow

        apply_chapter_file(document, file, nlp, chapter_repo, uow_factory)

        chapter, _ = _saved_chapter(uow)
        assert chapter.title == "Old Title"

    def test_changed_paragraph_replaces_sentences(self, nlp, tmp_path, header):
        file = tmp_path / "c1.md"
        file.write_text(f'{header}\n\n<span data-par-id="p1">New text.</span>')
        loaded = _make_chapter("c1", _make_paragraph("p1", "Old text."))
        document = _make_document("d1", _make_chapter("c1", _make_paragraph("p1", "Old text.")))
        chapter_repo, uow_factory = _setup(loaded)
        uow = MagicMock()
        uow_factory.get_unit_of_work.return_value = uow

        summary = apply_chapter_file(document, file, nlp, chapter_repo, uow_factory)

        chapter, kwargs = _saved_chapter(uow)
        assert chapter.state is DataState.CHANGED
        assert kwargs == {"document_id": "d1"}
        paragraph = chapter.paragraphs[0]
        assert paragraph.id == "p1"
        assert [s.get_text() for s in paragraph.sentences] == ["New text."]
        assert all(s.get_parent() is paragraph for s in paragraph.sentences)
        paragraphs = [m for m, kw in _saved_paragraphs(uow)]
        assert [p.id for p in paragraphs] == ["p1"]
        assert paragraphs[0].state is DataState.CHANGED
        assert summary.changed == 1
        uow.commit.assert_called_once()

    def test_deleted_paragraph_is_removed_and_not_registered(self, nlp, tmp_path, header):
        file = tmp_path / "c1.md"
        file.write_text(f'{header}\n\n<span data-par-id="p1">Only.</span>')
        loaded = _make_chapter("c1", _make_paragraph("p1", "Only."), _make_paragraph("p2", "Gone."))
        document = _make_document("d1", _make_chapter("c1", _make_paragraph("p1", "Only.")))
        chapter_repo, uow_factory = _setup(loaded)
        uow = MagicMock()
        uow_factory.get_unit_of_work.return_value = uow

        summary = apply_chapter_file(document, file, nlp, chapter_repo, uow_factory)

        chapter, _ = _saved_chapter(uow)
        assert [p.id for p in chapter.paragraphs] == ["p1"]
        assert all(model.id != "p2" for model, _ in _register_calls(uow))
        assert summary.deleted == 1
        uow.commit.assert_called_once()


class TestNewParagraphPlacement:
    def _write_spanned(self, tmp_path, header, body):
        file = tmp_path / "c1.md"
        file.write_text(f"{header}\n\n{body}")
        return file

    def test_run_of_new_paragraphs_after_anchor_keeps_file_order(self, nlp, tmp_path, header):
        chapter = _make_chapter("c1", _make_paragraph("pA", "A."), _make_paragraph("pB", "B."))
        file = self._write_spanned(
            tmp_path, header, '<span data-par-id="pA">A.</span>\n\nNew1.\n\nNew2.\n\n<span data-par-id="pB">B.</span>'
        )
        document = _make_document("d1", _make_chapter("c1", _make_paragraph("pA", "A."), _make_paragraph("pB", "B.")))
        chapter_repo, uow_factory = _setup(chapter)
        uow = MagicMock()
        uow_factory.get_unit_of_work.return_value = uow

        summary = apply_chapter_file(document, file, nlp, chapter_repo, uow_factory)

        saved, _ = _saved_chapter(uow)
        ids = [p.id for p in saved.paragraphs]
        assert len(set(ids)) == 4
        assert ids[0] == "pA"
        assert ids[3] == "pB"
        assert [p.sentences[0].get_text() for p in saved.paragraphs] == ["A.", "New1.", "New2.", "B."]
        assert summary.added == 2
        uow.commit.assert_called_once()

    def test_leading_new_paragraphs_go_first(self, nlp, tmp_path, header):
        chapter = _make_chapter("c1", _make_paragraph("pA", "A."))
        file = self._write_spanned(tmp_path, header, 'Lead.\n\n<span data-par-id="pA">A.</span>')
        document = _make_document("d1", _make_chapter("c1", _make_paragraph("pA", "A.")))
        chapter_repo, uow_factory = _setup(chapter)
        uow = MagicMock()
        uow_factory.get_unit_of_work.return_value = uow

        apply_chapter_file(document, file, nlp, chapter_repo, uow_factory)

        saved, _ = _saved_chapter(uow)
        assert [p.sentences[0].get_text() for p in saved.paragraphs] == ["Lead.", "A."]

    def test_single_new_paragraph_after_an_existing_anchor(self, nlp, tmp_path, header):
        chapter = _make_chapter("c1", _make_paragraph("pA", "A."), _make_paragraph("pB", "B."))
        file = self._write_spanned(tmp_path, header, '<span data-par-id="pA">A.</span>\n\nNew1.\n\n<span data-par-id="pB">B.</span>')
        document = _make_document("d1", _make_chapter("c1", _make_paragraph("pA", "A."), _make_paragraph("pB", "B.")))
        chapter_repo, uow_factory = _setup(chapter)
        uow = MagicMock()
        uow_factory.get_unit_of_work.return_value = uow

        apply_chapter_file(document, file, nlp, chapter_repo, uow_factory)

        saved, _ = _saved_chapter(uow)
        assert [p.sentences[0].get_text() for p in saved.paragraphs] == ["A.", "New1.", "B."]

    def test_leading_run_of_new_paragraphs_keeps_file_order(self, nlp, tmp_path, header):
        chapter = _make_chapter("c1", _make_paragraph("pA", "A."))
        file = self._write_spanned(tmp_path, header, 'Lead1.\n\nLead2.\n\n<span data-par-id="pA">A.</span>')
        document = _make_document("d1", _make_chapter("c1", _make_paragraph("pA", "A.")))
        chapter_repo, uow_factory = _setup(chapter)
        uow = MagicMock()
        uow_factory.get_unit_of_work.return_value = uow

        apply_chapter_file(document, file, nlp, chapter_repo, uow_factory)

        saved, _ = _saved_chapter(uow)
        assert [p.sentences[0].get_text() for p in saved.paragraphs] == ["Lead1.", "Lead2.", "A."]
