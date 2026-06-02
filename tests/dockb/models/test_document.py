"""Tests for Document model."""

import pytest

from dockb.models.chapter import Chapter
from dockb.models.document import Document
from dockb.models.paragraph import Paragraph
from dockb.models.sentence import Sentence
from dockb.models.utils.dockb_collection import InsertionMode


def test_each_document_has_unique_id():
    doc1 = Document()
    doc2 = Document()
    assert doc1.id != doc2.id
    assert isinstance(doc1.id, str)


def test_get_text_aggregates_children_when_not_dirty():
    doc = Document()
    doc.text = "Original"
    doc.dirty = False

    ch1 = Chapter()
    ch1.text = "Chapter One"
    ch1.dirty = False

    p1 = Paragraph()
    p1.text = "Para One"
    p1.dirty = False
    s1 = Sentence(text="Sentence One")
    s1.dirty = False
    p1.sentences.append(s1)

    ch1.paragraphs.append(p1)
    doc.chapters.append(ch1)

    # get_text should aggregate down to sentences
    assert doc.get_text() == "Sentence One"


def test_clear_semantics_removes_all_children(document):
    ch = Chapter()
    p = Paragraph()
    s = Sentence(text="Hello")
    p.sentences.append(s)
    ch.paragraphs.append(p)
    document.chapters.append(ch)

    document.clear_semantics()

    assert len(document.chapters) == 0
    assert len(ch.paragraphs) == 0
    assert len(p.sentences) == 0


def test_set_text_sets_dirty(document):
    document.set_text("Hello", _delay_semantics=True)
    assert document.text == "Hello"
    assert document.dirty


def test_insert_child_last_appends_chapter(document):
    ch1 = Chapter()
    ch2 = Chapter()
    document.chapters.append(ch1)
    document.chapters.append(ch2)
    document.insert_child(Chapter(), InsertionMode.LAST)

    assert len(document.chapters) == 3
    assert list(document.chapters)[0] is ch1
    assert list(document.chapters)[1] is ch2


def test_insert_child_first_prepends_chapter(document):
    ch1 = Chapter()
    ch2 = Chapter()
    document.chapters.append(ch1)
    document.chapters.append(ch2)
    first = Chapter()
    document.insert_child(first, InsertionMode.FIRST)

    assert len(document.chapters) == 3
    assert list(document.chapters)[0] is first
    assert list(document.chapters)[1] is ch1
    assert list(document.chapters)[2] is ch2


def test_insert_child_after_inserts_chapter_in_middle(document):
    ch1 = Chapter()
    ch2 = Chapter()
    document.chapters.append(ch1)
    document.chapters.append(ch2)
    middle = Chapter()
    document.insert_child(middle, InsertionMode.AFTER, ch1.id)

    assert len(document.chapters) == 3
    assert list(document.chapters)[0] is ch1
    assert list(document.chapters)[1] is middle
    assert list(document.chapters)[2] is ch2


def test_insert_child_chapter_sets_parent(document):
    ch = Chapter()
    document.insert_child(ch, InsertionMode.LAST)

    assert ch.get_parent() is document


def test_insert_child_raises_type_error_for_wrong_type(document):
    with pytest.raises(TypeError, match="Expected Chapter"):
        document.insert_child(Paragraph(), InsertionMode.LAST)
    with pytest.raises(TypeError, match="Expected Chapter"):
        document.insert_child(Sentence(), InsertionMode.LAST)
