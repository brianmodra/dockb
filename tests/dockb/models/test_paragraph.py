"""Tests for Paragraph model."""

import pytest

from dockb.models.chapter import Chapter
from dockb.models.paragraph import Paragraph
from dockb.models.sentence import Sentence
from dockb.models.utils.dockb_collection import InsertionMode


def test_each_paragraph_has_unique_id():
    p1 = Paragraph()
    p2 = Paragraph()
    assert p1.id != p2.id
    assert isinstance(p1.id, str)


def test_get_text_aggregates_children_when_not_dirty():
    para = Paragraph()
    para.text = "Original"
    para.dirty = False

    s1 = Sentence(text="Sentence One")
    s1.dirty = False
    s2 = Sentence(text="Sentence Two")
    s2.dirty = False
    para.sentences.extend([s1, s2])

    assert para.get_text() == "Sentence OneSentence Two"


def test_clear_semantics_removes_all_children(paragraph):
    s1 = Sentence(text="Hello")
    s2 = Sentence(text="World")
    paragraph.sentences.extend([s1, s2])

    paragraph.clear_semantics()

    assert len(paragraph.sentences) == 0


def test_set_text_sets_dirty(paragraph):
    paragraph.set_text("Hello")
    assert paragraph.text == "Hello"
    assert paragraph.dirty


def test_insert_child_last_appends_sentence(paragraph):
    s1 = Sentence()
    s2 = Sentence()
    paragraph.sentences.append(s1)
    paragraph.sentences.append(s2)
    paragraph.insert_child(Sentence(), InsertionMode.LAST)

    assert len(paragraph.sentences) == 3
    assert list(paragraph.sentences)[0] is s1
    assert list(paragraph.sentences)[1] is s2


def test_insert_child_first_prepends_sentence(paragraph):
    s1 = Sentence()
    s2 = Sentence()
    paragraph.sentences.append(s1)
    paragraph.sentences.append(s2)
    first = Sentence()
    paragraph.insert_child(first, InsertionMode.FIRST)

    assert len(paragraph.sentences) == 3
    assert list(paragraph.sentences)[0] is first
    assert list(paragraph.sentences)[1] is s1
    assert list(paragraph.sentences)[2] is s2


def test_insert_child_after_inserts_sentence_in_middle(paragraph):
    s1 = Sentence()
    s2 = Sentence()
    paragraph.sentences.append(s1)
    paragraph.sentences.append(s2)
    middle = Sentence()
    paragraph.insert_child(middle, InsertionMode.AFTER, s1.id)

    assert len(paragraph.sentences) == 3
    assert list(paragraph.sentences)[0] is s1
    assert list(paragraph.sentences)[1] is middle
    assert list(paragraph.sentences)[2] is s2


def test_insert_child_sentence_sets_parent(paragraph):
    s = Sentence()
    paragraph.insert_child(s, InsertionMode.LAST)

    assert s.get_parent() is paragraph


def test_insert_child_raises_type_error_for_wrong_type(paragraph):
    with pytest.raises(TypeError, match="Expected Sentence"):
        paragraph.insert_child(Chapter(), InsertionMode.LAST)
    with pytest.raises(TypeError, match="Expected Sentence"):
        paragraph.insert_child(Chapter(), InsertionMode.LAST)
