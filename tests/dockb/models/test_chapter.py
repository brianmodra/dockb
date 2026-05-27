"""Tests for Chapter text-editing operations inherited from DockbModel."""

import pytest

from dockb.exceptions import EditTextRangeError
from dockb.models.chapter import Chapter
from dockb.models.paragraph import Paragraph
from dockb.models.sentence import Sentence


@pytest.mark.parametrize(
    "operations, expected_text",
    [
        pytest.param([("append", "Hello World!")], "Hello World!", id="creates_text"),
        pytest.param(
            [("append", "Hello"), ("append", " World!")],
            "Hello World!",
            id="appends_text",
        ),
    ],
)
def test_apply_text_creates_or_appends_and_invalidates_semantics(chapter, operations, expected_text):
    for op, value in operations:
        if op == "append":
            chapter.apply_append_text(value)
    assert chapter.text == expected_text
    assert chapter.dirty


@pytest.mark.parametrize(
    "start, end, replacement, expected_text",
    [
        pytest.param(6, 10, "Sir", "Hello Sir!", id="replace_word"),
        pytest.param(11, 11, ".", "Hello World.", id="replace_single_char"),
        pytest.param(5, 10, "", "Hello!", id="empty_replacement_removes_text"),
    ],
)
def test_edit_text_replaces_text_and_invalidates_semantics(chapter, start, end, replacement, expected_text):
    chapter.apply_append_text("Hello World!")
    chapter.dirty = False
    chapter.apply_edit_text(start, end, replacement)
    assert chapter.text == expected_text
    assert chapter.dirty


@pytest.mark.parametrize(
    "start, end",
    [
        pytest.param(2, 1, id="end_before_start"),
        pytest.param(14, 14, id="start_out_of_range"),
        pytest.param(1, 15, id="end_out_of_range"),
        pytest.param(-1, 5, id="start_negative"),
        pytest.param(1, -1, id="end_negative"),
    ],
)
def test_edit_text_throws_for_invalid_ranges(chapter, start, end):
    chapter.apply_append_text("Hello World!")
    with pytest.raises(EditTextRangeError):
        chapter.apply_edit_text(start, end, "this won't work")


def test_edit_text_throws_when_no_existing_text(chapter):
    with pytest.raises(EditTextRangeError):
        chapter.apply_edit_text(0, 0, "this won't work")


@pytest.mark.parametrize(
    "pos, insertion, expected_text",
    [
        pytest.param(0, "Hello ", "Hello World!", id="beginning"),
        pytest.param(5, " World", "Hello World!", id="middle"),
        pytest.param(5, " World!", "Hello World!", id="end"),
    ],
)
def test_insert_text_and_invalidates_semantics(chapter, pos, insertion, expected_text):
    if pos == 0 and insertion == "Hello ":
        chapter.apply_append_text("World!")
    elif pos == 5 and insertion == " World":
        chapter.apply_append_text("Hello!")
    else:
        chapter.apply_append_text("Hello")
    chapter.dirty = False
    chapter.apply_insert_text(pos, insertion)
    assert chapter.text == expected_text
    assert chapter.dirty


def test_insert_text_into_empty_chapter_at_zero(chapter):
    chapter.apply_insert_text(0, "Hello World!")
    assert chapter.text == "Hello World!"
    assert chapter.dirty


@pytest.mark.parametrize(
    "pos, existing_text",
    [
        pytest.param(-1, "Hello World!", id="negative_pos"),
        pytest.param(14, "Hello World!", id="pos_out_of_range"),
        pytest.param(1, "", id="pos_out_of_range_with_no_text"),
    ],
)
def test_insert_text_throws_for_invalid_positions(chapter, pos, existing_text):
    if existing_text:
        chapter.apply_append_text(existing_text)
    with pytest.raises(EditTextRangeError):
        chapter.apply_insert_text(pos, "this won't work")


@pytest.mark.parametrize(
    "setup_text, pos, insertion",
    [
        pytest.param("Hello World!", 5, "", id="into_existing_text"),
        pytest.param("", 0, "", id="into_empty_chapter"),
    ],
)
def test_insert_text_with_empty_insertion_does_nothing(chapter, setup_text, pos, insertion):
    if setup_text:
        chapter.apply_append_text(setup_text)
    chapter.dirty = False
    chapter.apply_insert_text(pos, insertion)
    assert chapter.text == setup_text
    assert not chapter.dirty


@pytest.mark.parametrize(
    "existing_text",
    [
        pytest.param("", id="no_existing_text"),
        pytest.param("Hello", id="with_existing_text"),
    ],
)
def test_append_text_with_empty_string_does_nothing(chapter, existing_text):
    if existing_text:
        chapter.apply_append_text(existing_text)
        chapter.dirty = False
    chapter.apply_append_text("")
    assert chapter.text == existing_text
    assert not chapter.dirty


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


def test_set_text_with_delay_semantics(chapter):
    chapter.set_text("Hello", _delay_semantics=True)
    assert chapter.text == "Hello"
    assert chapter.dirty
