"""Tests for apply_chapter_file — the per-chapter-file markdown import caller."""

from __future__ import annotations

from pathlib import Path
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
from dockb.repositories.document_repository import DocumentRepository
from dockb.services import markdown_import
from dockb.services.markdown_import import (
    ChapterImportSummary,
    DocumentMetadata,
    _read_document_metadata,
    _resolve_document,
    _write_back_front_matter,
    apply_chapter_file,
    import_document_directory,
)


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


def _saved_sentences(uow):
    return [(model, kwargs) for model, kwargs in _register_calls(uow) if isinstance(model, Sentence)]


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

    def test_act_override_sets_act_on_created_chapter(self, nlp, tmp_path):
        file = tmp_path / "Chapter 1.md"
        file.write_text("Body.")
        document = _make_document("d1")
        chapter_repo, uow_factory = _setup(None)
        uow = MagicMock()
        uow_factory.get_unit_of_work.return_value = uow

        apply_chapter_file(document, file, nlp, chapter_repo, uow_factory, act="Act I")

        chapter, _ = _saved_chapter(uow)
        assert chapter.act == "Act I"
        assert "act: Act I" in file.read_text()

    def test_act_override_beats_front_matter_act(self, nlp, tmp_path):
        file = tmp_path / "Chapter 1.md"
        file.write_text('---\ntitle: Front Title\nact: "Act I"\n---\n\nBody.')
        document = _make_document("d1")
        chapter_repo, uow_factory = _setup(None)
        uow = MagicMock()
        uow_factory.get_unit_of_work.return_value = uow

        apply_chapter_file(document, file, nlp, chapter_repo, uow_factory, act="Act II")

        chapter, _ = _saved_chapter(uow)
        assert chapter.act == "Act II"

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

    def test_new_chapter_carries_act_from_front_matter(self, nlp, tmp_path):
        file = tmp_path / "Chapter 1.md"
        file.write_text('---\ntitle: Front Title\nact: "Act I"\n---\n\nBody.')
        document = _make_document("d1")
        chapter_repo, uow_factory = _setup(None)
        uow = MagicMock()
        uow_factory.get_unit_of_work.return_value = uow

        apply_chapter_file(document, file, nlp, chapter_repo, uow_factory)

        chapter, _ = _saved_chapter(uow)
        assert chapter.act == "Act I"

    def test_new_chapter_file_is_normalized_with_ids(self, nlp, tmp_path):
        file = tmp_path / "Chapter 2.md"
        file.write_text("Para one sentence.\n\nPara two sentence.")
        document = _make_document("d1")
        chapter_repo, uow_factory = _setup(None)
        uow = MagicMock()
        uow_factory.get_unit_of_work.return_value = uow

        summary = apply_chapter_file(document, file, nlp, chapter_repo, uow_factory)

        rewritten = file.read_text()
        assert rewritten.startswith(f"---\nid: {summary.chapter_id}\ntitle: Chapter 2\n---\n")
        assert "Para one sentence." in rewritten
        assert "Para two sentence." in rewritten
        assert rewritten.count('<span data-par-id="') == 2

    def test_empty_new_chapter_persists_identity(self, nlp, tmp_path):
        file = tmp_path / "Empty.md"
        file.write_text("")
        document = _make_document("d1")
        chapter_repo, uow_factory = _setup(None)
        uow = MagicMock()
        uow_factory.get_unit_of_work.return_value = uow

        summary = apply_chapter_file(document, file, nlp, chapter_repo, uow_factory)

        assert summary.created is True
        chapter, kwargs = _saved_chapter(uow)
        assert chapter.id == summary.chapter_id
        assert kwargs == {"document_id": "d1"}
        assert file.read_text() == f"---\nid: {summary.chapter_id}\ntitle: Empty\n---\n"

    def test_empty_new_chapter_reimport_is_a_no_op(self, nlp, tmp_path):
        file = tmp_path / "Empty.md"
        file.write_text("")
        document = _make_document("d1")
        chapter_repo, uow_factory = _setup(None)
        uow_factory.get_unit_of_work.return_value = MagicMock()

        first = apply_chapter_file(document, file, nlp, chapter_repo, uow_factory)
        persisted = Chapter(id=first.chapter_id, title="Empty", state=DataState.SYNC)
        document.append_child(persisted)
        chapter_repo.load.return_value = persisted
        written = file.read_text()

        second = apply_chapter_file(document, file, nlp, chapter_repo, uow_factory)

        assert second.created is False
        assert file.read_text() == written


class TestSingleNewlineParagraphs:
    def test_loose_single_newline_file_imports_lines_as_paragraphs(self, nlp, tmp_path):
        file = tmp_path / "Loose.md"
        file.write_text("First paragraph sentence one. Second sentence.\nSecond paragraph sentence.")
        document = _make_document("d1")
        chapter_repo, uow_factory = _setup(None)
        uow = MagicMock()
        uow_factory.get_unit_of_work.return_value = uow

        summary = apply_chapter_file(document, file, nlp, chapter_repo, uow_factory, single_newline_paragraphs=True)

        assert summary.created is True
        assert summary.added == 2
        chapter, _ = _saved_chapter(uow)
        assert [s.get_text() for p in chapter.paragraphs for s in p.sentences] == [
            "First paragraph sentence one. ",
            "Second sentence.",
            "Second paragraph sentence.",
        ]
        rewritten = file.read_text()
        assert rewritten.count('<span data-par-id="') == 2
        assert "\n\n<span data-par-id=" in rewritten
        assert "First paragraph sentence one.\nSecond sentence.\n</span>" in rewritten

    def test_single_newline_mode_keeps_canonical_file_unchanged(self, nlp, tmp_path, header):
        def paragraphs():
            return [
                _make_paragraph("p1", "First sentence.\n", "Second sentence."),
                _make_paragraph("p2", "Third sentence."),
            ]

        file = tmp_path / "Loose.md"
        file.write_text(
            f"{header}\n\n"
            '<span data-par-id="p1">\nFirst sentence.\nSecond sentence.\n</span>\n\n'
            '<span data-par-id="p2">\nThird sentence.\n</span>'
        )
        loaded = _make_chapter("c1", *paragraphs())
        document = _make_document("d1", _make_chapter("c1", *paragraphs()))
        chapter_repo, uow_factory = _setup(loaded)
        uow = MagicMock()
        uow_factory.get_unit_of_work.return_value = uow

        summary = apply_chapter_file(document, file, nlp, chapter_repo, uow_factory, single_newline_paragraphs=True)

        assert summary.added == summary.changed == summary.deleted == 0
        uow.register.assert_not_called()
        uow.commit.assert_not_called()
        written = (
            f"{header}\n\n"
            '<span data-par-id="p1">\nFirst sentence.\nSecond sentence.\n</span>\n\n'
            '<span data-par-id="p2">\nThird sentence.\n</span>'
        )
        assert file.read_text() == written


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

    def test_act_override_updates_existing_chapter(self, nlp, tmp_path, header):
        file = tmp_path / "c1.md"
        file.write_text(f'{header}\n\n<span data-par-id="p1">New text.</span>')
        loaded = _make_chapter("c1", _make_paragraph("p1", "Old text."))
        loaded.act = "Act I"
        document = _make_document("d1", _make_chapter("c1", _make_paragraph("p1", "Old text.")))
        chapter_repo, uow_factory = _setup(loaded)
        uow = MagicMock()
        uow_factory.get_unit_of_work.return_value = uow

        apply_chapter_file(document, file, nlp, chapter_repo, uow_factory, act="Act II")

        chapter, _ = _saved_chapter(uow)
        assert chapter.act == "Act II"
        assert "act: Act II" in file.read_text()

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
        assert file.read_text() == f'{header}\n\n<span data-par-id="p1">Only.</span>'

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

    def test_changed_paragraph_writes_back_front_matter_and_body(self, nlp, tmp_path):
        file = tmp_path / "c1.md"
        file.write_text('---\nauthor: Brian\ntitle: Old Title\nid: c1\n---\n\n<span data-par-id="p1">New text.</span>')
        loaded = _make_chapter("c1", _make_paragraph("p1", "Old text."))
        document = _make_document("d1", _make_chapter("c1", _make_paragraph("p1", "Old text.")))
        chapter_repo, uow_factory = _setup(loaded)
        uow = MagicMock()
        uow_factory.get_unit_of_work.return_value = uow

        summary = apply_chapter_file(document, file, nlp, chapter_repo, uow_factory)

        assert summary.changed == 1
        assert file.read_text() == '---\nauthor: Brian\ntitle: Old Title\nid: c1\n---\n\n<span data-par-id="p1">\nNew text.\n</span>\n'

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

    def test_new_chapter_registers_sentences_with_tokens(self, nlp, tmp_path):
        file = tmp_path / "c1.md"
        file.write_text("First sentence. Second sentence.\n\nAnother paragraph.")
        document = _make_document("d1")
        chapter_repo, uow_factory = _setup(None)
        uow = MagicMock()
        uow_factory.get_unit_of_work.return_value = uow

        summary = apply_chapter_file(document, file, nlp, chapter_repo, uow_factory)

        sentences = [model for model, _ in _saved_sentences(uow)]
        assert len(sentences) == 3
        for sentence in sentences:
            assert sentence.state is DataState.NEW
            assert list(sentence.tokens), f"expected tokens for {sentence.text!r}"
            assert sentence.get_text() == sentence.text, "tokenization must round-trip the sentence text"
        assert summary.added == 2

    def test_changed_paragraph_registers_replacement_sentences(self, nlp, tmp_path, header):
        file = tmp_path / "c1.md"
        file.write_text(f'{header}\n\n<span data-par-id="p1">New text.</span>')
        loaded = _make_chapter("c1", _make_paragraph("p1", "Old text."))
        document = _make_document("d1", _make_chapter("c1", _make_paragraph("p1", "Old text.")))
        chapter_repo, uow_factory = _setup(loaded)
        uow = MagicMock()
        uow_factory.get_unit_of_work.return_value = uow

        summary = apply_chapter_file(document, file, nlp, chapter_repo, uow_factory)

        sentences = [model for model, _ in _saved_sentences(uow)]
        assert len(sentences) == 1
        assert sentences[0].state is DataState.NEW
        assert sentences[0].get_text() == "New text."
        assert list(sentences[0].tokens)
        assert summary.changed == 1


class TestApplyChapterFileTiming:
    """apply_chapter_file records its sub-stages in the active trace."""

    @staticmethod
    def _names(timings) -> list[str]:
        return [part.split(" ")[0] for part in timings.summary().split(", ")]

    def test_changed_apply_records_parse_spacy_persist_render(self, nlp, tmp_path) -> None:
        from dockb.timing import trace

        file = tmp_path / "c1.md"
        file.write_text('<span data-par-id="p1">New text.</span>')
        loaded = _make_chapter("c1", _make_paragraph("p1", "Old text."))
        document = _make_document("d1", _make_chapter("c1", _make_paragraph("p1", "Old text.")))
        chapter_repo, uow_factory = _setup(loaded)
        uow = MagicMock()
        uow_factory.get_unit_of_work.return_value = uow

        with trace() as timings:
            apply_chapter_file(document, file, nlp, chapter_repo, uow_factory)

        assert self._names(timings) == [
            "stage.parse_file",
            "stage.spacy",
            "stage.persist",
            "stage.render",
        ]

    def test_unchanged_apply_records_only_parse(self, nlp, tmp_path) -> None:
        from dockb.timing import trace

        file = tmp_path / "Empty.md"
        file.write_text("")
        document = _make_document("d1")
        chapter_repo, uow_factory = _setup(None)
        uow_factory.get_unit_of_work.return_value = MagicMock()

        first = apply_chapter_file(document, file, nlp, chapter_repo, uow_factory)
        persisted = Chapter(id=first.chapter_id, title="Empty", state=DataState.SYNC)
        document.append_child(persisted)
        chapter_repo.load.return_value = persisted

        with trace() as timings:
            apply_chapter_file(document, file, nlp, chapter_repo, uow_factory)

        assert self._names(timings) == ["stage.parse_file"]

    def test_created_apply_records_parse_spacy_persist_render(self, nlp, tmp_path) -> None:
        from dockb.timing import trace

        file = tmp_path / "Chapter 1.md"
        file.write_text("Para one sentence.\n\nPara two sentence.")
        document = _make_document("d1")
        chapter_repo, uow_factory = _setup(None)
        uow = MagicMock()
        uow_factory.get_unit_of_work.return_value = uow

        with trace() as timings:
            apply_chapter_file(document, file, nlp, chapter_repo, uow_factory)

        assert self._names(timings) == [
            "stage.parse_file",
            "stage.spacy",
            "stage.persist",
            "stage.render",
        ]


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


class TestDocumentMetadata:
    def test_reads_title_and_author_from_yaml(self, tmp_path):
        (tmp_path / "document_metadata.yaml").write_text("title: Linchpin\nauthor: Brian\n")
        metadata = _read_document_metadata(tmp_path, "User")
        assert metadata.title == "Linchpin"
        assert metadata.author == "Brian"

    def test_missing_file_defaults_to_dir_name_and_user(self, tmp_path):
        metadata = _read_document_metadata(tmp_path, "User")
        assert metadata.title == tmp_path.name
        assert metadata.author == "User"

    def test_partial_metadata_falls_back_for_missing_field(self, tmp_path):
        (tmp_path / "document_metadata.yaml").write_text("title: Linchpin\n")
        metadata = _read_document_metadata(tmp_path, "User")
        assert metadata.title == "Linchpin"
        assert metadata.author == "User"

    def test_non_dict_yaml_is_ignored(self, tmp_path):
        (tmp_path / "document_metadata.yaml").write_text("- a\n- b\n")
        metadata = _read_document_metadata(tmp_path, "User")
        assert metadata.title == tmp_path.name
        assert metadata.author == "User"


class TestResolveDocument:
    def _repo_with(self, rows):
        repo = MagicMock(spec=DocumentRepository)
        repo.list_all.return_value = rows
        return repo

    def test_reuses_existing_document_by_title(self):
        repo = self._repo_with([{"id": "d1", "title": "Linchpin", "author": "A"}])
        loaded = Document(id="d1", state=DataState.SYNC)
        repo.load.return_value = loaded
        uow_factory = MagicMock()

        result = _resolve_document(Path("Linchpin"), DocumentMetadata("Linchpin", "User"), repo, uow_factory)

        assert result is loaded
        repo.load.assert_called_once_with("d1")
        uow_factory.get_unit_of_work.assert_not_called()

    def test_matches_title_case_insensitively(self):
        repo = self._repo_with([{"id": "d1", "title": "Linchpin", "author": "A"}])
        loaded = Document(id="d1", state=DataState.SYNC)
        repo.load.return_value = loaded
        uow_factory = MagicMock()

        result = _resolve_document(Path("linchpin"), DocumentMetadata("LINCHPIN", "User"), repo, uow_factory)

        assert result is loaded
        uow_factory.get_unit_of_work.assert_not_called()

    def test_multiple_matches_uses_first(self):
        repo = self._repo_with([{"id": "d1", "title": "Linchpin", "author": "A"}, {"id": "d2", "title": "Linchpin", "author": "A"}])
        loaded = Document(id="d1", state=DataState.SYNC)
        repo.load.return_value = loaded
        uow_factory = MagicMock()

        result = _resolve_document(Path("Linchpin"), DocumentMetadata("Linchpin", "User"), repo, uow_factory)

        assert result is loaded
        repo.load.assert_called_once_with("d1")

    def test_created_document_writes_metadata_file(self, tmp_path):
        repo = self._repo_with([])
        uow = MagicMock()
        uow_factory = MagicMock()
        uow_factory.get_unit_of_work.return_value = uow

        _resolve_document(tmp_path, DocumentMetadata("Linchpin", "User"), repo, uow_factory)

        assert (tmp_path / "document_metadata.yaml").read_text() == "title: Linchpin\nauthor: User\n"

    def test_created_document_preserves_existing_metadata_keys(self, tmp_path):
        (tmp_path / "document_metadata.yaml").write_text("isbn: 123\n")
        repo = self._repo_with([])
        uow = MagicMock()
        uow_factory = MagicMock()
        uow_factory.get_unit_of_work.return_value = uow

        _resolve_document(tmp_path, DocumentMetadata("Linchpin", "User"), repo, uow_factory)

        assert (tmp_path / "document_metadata.yaml").read_text() == "isbn: 123\ntitle: Linchpin\nauthor: User\n"

    def test_existing_document_leaves_metadata_file_untouched(self, tmp_path):
        metadata_file = tmp_path / "document_metadata.yaml"
        metadata_file.write_text("title: Linchpin\nauthor: A\n")
        repo = self._repo_with([{"id": "d1", "title": "Linchpin", "author": "A"}])
        loaded = Document(id="d1", state=DataState.SYNC)
        repo.load.return_value = loaded
        uow_factory = MagicMock()

        _resolve_document(tmp_path, DocumentMetadata("Linchpin", "User"), repo, uow_factory)

        assert metadata_file.read_text() == "title: Linchpin\nauthor: A\n"

    def test_creates_new_document_when_no_match(self, tmp_path):
        repo = self._repo_with([])
        uow = MagicMock()
        uow_factory = MagicMock()
        uow_factory.get_unit_of_work.return_value = uow

        result = _resolve_document(tmp_path, DocumentMetadata("Linchpin", "User"), repo, uow_factory)

        assert isinstance(result, Document)
        assert result.id != "d1"
        assert result.title == "Linchpin"
        assert result.author == "User"
        assert result.state is DataState.NEW
        uow.register.assert_called_once_with(result)
        uow.commit.assert_called_once()

    def test_creates_when_load_misses(self, tmp_path):
        repo = self._repo_with([{"id": "d1", "title": "Linchpin", "author": "A"}])
        repo.load.return_value = None
        uow = MagicMock()
        uow_factory = MagicMock()
        uow_factory.get_unit_of_work.return_value = uow

        result = _resolve_document(tmp_path, DocumentMetadata("Linchpin", "User"), repo, uow_factory)

        assert result.state is DataState.NEW
        assert result.title == "Linchpin"
        uow.register.assert_called_once_with(result)
        uow.commit.assert_called_once()


class TestImportDocumentDirectory:
    def test_imports_act_dirs_only_in_number_sequence_order(self, nlp, tmp_path, monkeypatch):
        (tmp_path / "Chapter 0.md").write_text("root file - not a chapter")
        (tmp_path / "drafts").mkdir()
        (tmp_path / "drafts" / "Draft.md").write_text("non-act dir - not a chapter")
        act_i = tmp_path / "Act I"
        act_i.mkdir()
        act_ii = tmp_path / "Act II" / "deeper"
        act_ii.mkdir(parents=True)
        for name in [
            "Opening 1.md",
            "Setup 10.md",
            "Setup 2.md",
            "Setup 5.md",
            "Setup 5b.md",
            "Setup 6.md",
        ]:
            (act_i / name).write_text("a")
        (act_ii / "Opening 3.md").write_text("c")

        document = Document(id="d1", state=DataState.SYNC)
        document_repo = MagicMock(spec=DocumentRepository)
        document_repo.list_all.return_value = [{"id": "d1", "title": tmp_path.name, "author": "User"}]
        document_repo.load.return_value = document
        chapter_repo = MagicMock(spec=ChapterRepository)
        uow_factory = MagicMock()
        summaries = [ChapterImportSummary(chapter_id=f"c{i}", created=True) for i in range(7)]
        calls: list[tuple] = []

        def fake_apply(*args, **kwargs):
            calls.append((args, kwargs))
            return summaries[len(calls) - 1]

        monkeypatch.setattr(markdown_import, "apply_chapter_file", fake_apply)

        result = import_document_directory(tmp_path, "User", nlp, document_repo, chapter_repo, uow_factory)

        assert result == summaries
        assert [Path(args[1]).name for args, _ in calls] == [
            "Opening 1.md",
            "Setup 2.md",
            "Setup 5.md",
            "Setup 5b.md",
            "Setup 6.md",
            "Setup 10.md",
            "Opening 3.md",
        ]
        assert [kwargs["act"] for _, kwargs in calls] == [
            "Act I",
            "Act I",
            "Act I",
            "Act I",
            "Act I",
            "Act I",
            "Act II",
        ]
        assert all(args[0] is document for args, _ in calls)
        assert all(args[2] is nlp for args, _ in calls)
        assert all(args[3] is chapter_repo for args, _ in calls)
        assert all(args[4] is uow_factory for args, _ in calls)

    def test_act_none_directory_maps_to_empty_act(self, nlp, tmp_path, monkeypatch):
        act_none = tmp_path / "Act None"
        act_none.mkdir()
        (act_none / "Chapter 1.md").write_text("a")
        document = Document(id="d1", state=DataState.SYNC)
        document_repo = MagicMock(spec=DocumentRepository)
        document_repo.list_all.return_value = [{"id": "d1", "title": tmp_path.name, "author": "User"}]
        document_repo.load.return_value = document
        acts: list[str] = []

        def fake_apply(*_args, **kwargs):
            acts.append(kwargs["act"])
            return ChapterImportSummary(chapter_id="c1", created=True)

        monkeypatch.setattr(markdown_import, "apply_chapter_file", fake_apply)

        import_document_directory(tmp_path, "User", nlp, document_repo, MagicMock(), MagicMock())

        assert acts == [""]

    def test_non_act_top_level_subdirectories_are_skipped(self, nlp, tmp_path, monkeypatch):
        (tmp_path / "drafts").mkdir()
        (tmp_path / "drafts" / "Draft.md").write_text("a")
        document = Document(id="d1", state=DataState.SYNC)
        monkeypatch.setattr(markdown_import, "_resolve_document", lambda *a: document)
        monkeypatch.setattr(
            markdown_import,
            "apply_chapter_file",
            lambda *a, **_k: (_ for _ in ()).throw(AssertionError("no chapter file expected")),
        )

        result = import_document_directory(tmp_path, "User", nlp, None, None, None)

        assert not result

    def test_resolves_document_via_metadata_helpers(self, nlp, tmp_path, monkeypatch):
        act = tmp_path / "Act I"
        act.mkdir()
        (act / "Opening 1.md").write_text("a")
        document = Document(id="d1", state=DataState.SYNC)
        resolved: list[tuple] = []
        chapter_repo = MagicMock(spec=ChapterRepository)
        uow_factory = MagicMock()
        monkeypatch.setattr(markdown_import, "_read_document_metadata", lambda d, u: DocumentMetadata("T", u))
        monkeypatch.setattr(
            markdown_import,
            "_resolve_document",
            lambda d, metadata, document_repo, uow_factory: resolved.append((d, metadata)) or document,
        )
        monkeypatch.setattr(
            markdown_import,
            "apply_chapter_file",
            lambda document, file, nlp, chapter_repo, uow_factory, **_kwargs: ChapterImportSummary("c1", False),
        )

        import_document_directory(tmp_path, "User", nlp, MagicMock(), chapter_repo, uow_factory)

        assert resolved == [(tmp_path, DocumentMetadata("T", "User"))]

    def test_no_chapter_files_returns_empty(self, nlp, tmp_path, monkeypatch):
        document = Document(id="d1", state=DataState.SYNC)
        monkeypatch.setattr(markdown_import, "_resolve_document", lambda *a: document)
        monkeypatch.setattr(
            markdown_import,
            "apply_chapter_file",
            lambda *a: (_ for _ in ()).throw(AssertionError("no chapter file expected")),
        )

        result = import_document_directory(tmp_path, "User", nlp, None, None, None)

        assert not result

    def test_missing_directory_raises(self, nlp, tmp_path):
        with pytest.raises(ValueError, match="does not exist"):
            import_document_directory(tmp_path / "nope", "User", nlp, None, None, None)


class TestWriteBackFrontMatter:
    def test_prepends_front_matter_when_absent(self, tmp_path):
        chapter_file = tmp_path / "new.md"
        chapter_file.write_text("# Ch\n\nbody\n")

        _write_back_front_matter(chapter_file, ChapterImportSummary(chapter_id="c1", created=True, title="Ch"))

        assert chapter_file.read_text() == "---\nid: c1\ntitle: Ch\n---\n# Ch\n\nbody\n"

    def test_merges_id_and_title_into_existing_front_matter(self, tmp_path):
        chapter_file = tmp_path / "new.md"
        chapter_file.write_text("---\nfoo: bar\n---\nbody\n")

        _write_back_front_matter(chapter_file, ChapterImportSummary(chapter_id="c1", created=True, title="T"))

        assert chapter_file.read_text() == "---\nfoo: bar\nid: c1\ntitle: T\n---\nbody\n"

    def test_keeps_existing_id_when_other_attrs_present(self, tmp_path):
        chapter_file = tmp_path / "new.md"
        chapter_file.write_text("---\nauthor: Brian\n---\nbody\n")

        _write_back_front_matter(chapter_file, ChapterImportSummary(chapter_id="c9", created=True, title="T"))

        assert "author: Brian\n" in chapter_file.read_text()
        assert "id: c9\n" in chapter_file.read_text()

    def test_unclosed_front_matter_raises(self, tmp_path):
        chapter_file = tmp_path / "new.md"
        chapter_file.write_text("---\nfoo: bar\nbody\n")

        with pytest.raises(ChapterMismatchError, match="closing"):
            _write_back_front_matter(chapter_file, ChapterImportSummary(chapter_id="c1", created=True, title="T"))

    def test_walker_leaves_chapter_files_to_apply_chapter_file(self, nlp, tmp_path, monkeypatch):
        act = tmp_path / "Act I"
        act.mkdir()
        new_file = act / "Opening 1.md"
        new_file.write_text("fresh")
        document = Document(id="d1", state=DataState.SYNC)
        monkeypatch.setattr(markdown_import, "_resolve_document", lambda *a: document)

        def fake_apply(*_args, **_kwargs):
            return ChapterImportSummary(chapter_id="c-new", created=True, title="New")

        monkeypatch.setattr(markdown_import, "apply_chapter_file", fake_apply)

        import_document_directory(tmp_path, "User", nlp, None, MagicMock(spec=ChapterRepository), MagicMock())

        assert new_file.read_text() == "fresh"
