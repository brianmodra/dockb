"""Tests for Paragraph text-editing operations inherited from DockbModel."""

import pytest

from dockb.exceptions import EditTextRangeError
from dockb.models.paragraph import Paragraph


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
def test_apply_text_creates_or_appends_and_invalidates_semantics(paragraph, operations, expected_text):
    for op, value in operations:
        if op == "append":
            paragraph.apply_append_text(value)
    assert paragraph.text == expected_text
    assert paragraph.dirty


@pytest.mark.parametrize(
    "start, end, replacement, expected_text",
    [
        pytest.param(6, 10, "Sir", "Hello Sir!", id="replace_word"),
        pytest.param(11, 11, ".", "Hello World.", id="replace_single_char"),
        pytest.param(5, 10, "", "Hello!", id="empty_replacement_removes_text"),
    ],
)
def test_edit_text_replaces_text_and_invalidates_semantics(paragraph, start, end, replacement, expected_text):
    paragraph.apply_append_text("Hello World!")
    paragraph.dirty = False
    paragraph.apply_edit_text(start, end, replacement)
    assert paragraph.text == expected_text
    assert paragraph.dirty


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
def test_edit_text_throws_for_invalid_ranges(paragraph, start, end):
    paragraph.apply_append_text("Hello World!")
    with pytest.raises(EditTextRangeError):
        paragraph.apply_edit_text(start, end, "this won't work")


def test_edit_text_throws_when_no_existing_text(paragraph):
    with pytest.raises(EditTextRangeError):
        paragraph.apply_edit_text(0, 0, "this won't work")


@pytest.mark.parametrize(
    "pos, insertion, expected_text",
    [
        pytest.param(0, "Hello ", "Hello World!", id="beginning"),
        pytest.param(5, " World", "Hello World!", id="middle"),
        pytest.param(5, " World!", "Hello World!", id="end"),
    ],
)
def test_insert_text_and_invalidates_semantics(paragraph, pos, insertion, expected_text):
    if pos == 0 and insertion == "Hello ":
        paragraph.apply_append_text("World!")
    elif pos == 5 and insertion == " World":
        paragraph.apply_append_text("Hello!")
    else:
        paragraph.apply_append_text("Hello")
    paragraph.dirty = False
    paragraph.apply_insert_text(pos, insertion)
    assert paragraph.text == expected_text
    assert paragraph.dirty


def test_insert_text_into_empty_paragraph_at_zero(paragraph):
    paragraph.apply_insert_text(0, "Hello World!")
    assert paragraph.text == "Hello World!"
    assert paragraph.dirty


@pytest.mark.parametrize(
    "pos, existing_text",
    [
        pytest.param(-1, "Hello World!", id="negative_pos"),
        pytest.param(14, "Hello World!", id="pos_out_of_range"),
        pytest.param(1, "", id="pos_out_of_range_with_no_text"),
    ],
)
def test_insert_text_throws_for_invalid_positions(paragraph, pos, existing_text):
    if existing_text:
        paragraph.apply_append_text(existing_text)
    with pytest.raises(EditTextRangeError):
        paragraph.apply_insert_text(pos, "this won't work")


@pytest.mark.parametrize(
    "setup_text, pos, insertion",
    [
        pytest.param("Hello World!", 5, "", id="into_existing_text"),
        pytest.param("", 0, "", id="into_empty_paragraph"),
    ],
)
def test_insert_text_with_empty_insertion_does_nothing(paragraph, setup_text, pos, insertion):
    if setup_text:
        paragraph.apply_append_text(setup_text)
    paragraph.dirty = False
    paragraph.apply_insert_text(pos, insertion)
    assert paragraph.text == setup_text
    assert not paragraph.dirty


@pytest.mark.parametrize(
    "existing_text",
    [
        pytest.param("", id="no_existing_text"),
        pytest.param("Hello", id="with_existing_text"),
    ],
)
def test_append_text_with_empty_string_does_nothing(paragraph, existing_text):
    if existing_text:
        paragraph.apply_append_text(existing_text)
        paragraph.dirty = False
    paragraph.apply_append_text("")
    assert paragraph.text == existing_text
    assert not paragraph.dirty


def test_each_paragraph_has_unique_id():
    p1 = Paragraph()
    p2 = Paragraph()
    assert p1.id != p2.id
    assert isinstance(p1.id, str)


def test_get_text_aggregates_children_when_not_dirty():
    from dockb.models.sentence import Sentence

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
    from dockb.models.sentence import Sentence

    s1 = Sentence(text="Hello")
    s2 = Sentence(text="World")
    paragraph.sentences.extend([s1, s2])

    paragraph.clear_semantics()

    assert len(paragraph.sentences) == 0


def test_set_text_with_delay_semantics(paragraph):
    paragraph.set_text("Hello", _delay_semantics=True)
    assert paragraph.text == "Hello"
    assert paragraph.dirty
