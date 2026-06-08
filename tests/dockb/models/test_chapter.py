"""Tests for Chapter model."""

import pytest

from dockb.models.chapter import Chapter
from dockb.models.paragraph import Paragraph
from dockb.models.sentence import Sentence
from dockb.models.utils.dockb_collection import InsertionMode


def test_each_chapter_has_unique_id():
    c1 = Chapter()
    c2 = Chapter()
    assert c1.id != c2.id
    assert isinstance(c1.id, str)


def test_get_text_aggregates_children_when_not_dirty():
    ch = Chapter()
    ch.text = "Original"
    ch.dirty = False

    p1 = Paragraph(text="Para One")
    p1.dirty = False
    p2 = Paragraph(text="Para Two")
    p2.dirty = False
    ch.paragraphs.extend([p1, p2])

    assert ch.get_text() == "Para OnePara Two"


def test_clear_semantics_removes_all_children(chapter):
    p = Paragraph()
    s = Sentence(text="Hello")
    p.sentences.append(s)
    chapter.paragraphs.append(p)

    chapter.clear_semantics()

    assert len(chapter.paragraphs) == 0
    assert len(p.sentences) == 0


def test_set_text_sets_dirty(chapter):
    chapter.set_text("Hello")
    assert chapter.text == "Hello"
    assert chapter.dirty


def test_insert_child_last_appends_paragraph(chapter):
    p1 = Paragraph()
    p2 = Paragraph()
    chapter.paragraphs.append(p1)
    chapter.paragraphs.append(p2)
    chapter.insert_child(Paragraph(), InsertionMode.LAST)

    assert len(chapter.paragraphs) == 3
    assert list(chapter.paragraphs)[0] is p1
    assert list(chapter.paragraphs)[1] is p2


def test_insert_child_first_prepends_paragraph(chapter):
    p1 = Paragraph()
    p2 = Paragraph()
    chapter.paragraphs.append(p1)
    chapter.paragraphs.append(p2)
    first = Paragraph()
    chapter.insert_child(first, InsertionMode.FIRST)

    assert len(chapter.paragraphs) == 3
    assert list(chapter.paragraphs)[0] is first
    assert list(chapter.paragraphs)[1] is p1
    assert list(chapter.paragraphs)[2] is p2


def test_insert_child_after_inserts_paragraph_in_middle(chapter):
    p1 = Paragraph()
    p2 = Paragraph()
    chapter.paragraphs.append(p1)
    chapter.paragraphs.append(p2)
    middle = Paragraph()
    chapter.insert_child(middle, InsertionMode.AFTER, p1.id)

    assert len(chapter.paragraphs) == 3
    assert list(chapter.paragraphs)[0] is p1
    assert list(chapter.paragraphs)[1] is middle
    assert list(chapter.paragraphs)[2] is p2


def test_insert_child_paragraph_sets_parent(chapter):
    p = Paragraph()
    chapter.insert_child(p, InsertionMode.LAST)

    assert p.get_parent() is chapter


def test_insert_child_raises_type_error_for_wrong_type(chapter):
    with pytest.raises(TypeError, match="Expected Paragraph"):
        chapter.insert_child(Sentence(), InsertionMode.LAST)
    with pytest.raises(TypeError, match="Expected Paragraph"):
        chapter.insert_child(Sentence(), InsertionMode.LAST)
