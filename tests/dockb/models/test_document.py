"""Tests for Document text-editing operations inherited from DockbModel."""

import pytest

from dockb.exceptions import EditTextRangeError
from dockb.models.document import Document


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
def test_apply_text_creates_or_appends_and_invalidates_semantics(document, operations, expected_text):
    for op, value in operations:
        if op == "append":
            document.apply_append_text(value)
    assert document.text == expected_text
    assert document.dirty


@pytest.mark.parametrize(
    "start, end, replacement, expected_text",
    [
        pytest.param(6, 10, "Sir", "Hello Sir!", id="replace_word"),
        pytest.param(11, 11, ".", "Hello World.", id="replace_single_char"),
        pytest.param(5, 10, "", "Hello!", id="empty_replacement_removes_text"),
    ],
)
def test_edit_text_replaces_text_and_invalidates_semantics(document, start, end, replacement, expected_text):
    document.apply_append_text("Hello World!")
    document.dirty = False
    document.apply_edit_text(start, end, replacement)
    assert document.text == expected_text
    assert document.dirty


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
def test_edit_text_throws_for_invalid_ranges(document, start, end):
    document.apply_append_text("Hello World!")
    with pytest.raises(EditTextRangeError):
        document.apply_edit_text(start, end, "this won't work")


def test_edit_text_throws_when_no_existing_text(document):
    with pytest.raises(EditTextRangeError):
        document.apply_edit_text(0, 0, "this won't work")


@pytest.mark.parametrize(
    "pos, insertion, expected_text",
    [
        pytest.param(0, "Hello ", "Hello World!", id="beginning"),
        pytest.param(5, " World", "Hello World!", id="middle"),
        pytest.param(5, " World!", "Hello World!", id="end"),
    ],
)
def test_insert_text_and_invalidates_semantics(document, pos, insertion, expected_text):
    if pos == 0 and insertion == "Hello ":
        document.apply_append_text("World!")
    elif pos == 5 and insertion == " World":
        document.apply_append_text("Hello!")
    else:
        document.apply_append_text("Hello")
    document.dirty = False
    document.apply_insert_text(pos, insertion)
    assert document.text == expected_text
    assert document.dirty


def test_insert_text_into_empty_document_at_zero(document):
    document.apply_insert_text(0, "Hello World!")
    assert document.text == "Hello World!"
    assert document.dirty


@pytest.mark.parametrize(
    "pos, existing_text",
    [
        pytest.param(-1, "Hello World!", id="negative_pos"),
        pytest.param(14, "Hello World!", id="pos_out_of_range"),
        pytest.param(1, "", id="pos_out_of_range_with_no_text"),
    ],
)
def test_insert_text_throws_for_invalid_positions(document, pos, existing_text):
    if existing_text:
        document.apply_append_text(existing_text)
    with pytest.raises(EditTextRangeError):
        document.apply_insert_text(pos, "this won't work")


@pytest.mark.parametrize(
    "setup_text, pos, insertion",
    [
        pytest.param("Hello World!", 5, "", id="into_existing_text"),
        pytest.param("", 0, "", id="into_empty_document"),
    ],
)
def test_insert_text_with_empty_insertion_does_nothing(document, setup_text, pos, insertion):
    if setup_text:
        document.apply_append_text(setup_text)
    document.dirty = False
    document.apply_insert_text(pos, insertion)
    assert document.text == setup_text
    assert not document.dirty


@pytest.mark.parametrize(
    "existing_text",
    [
        pytest.param("", id="no_existing_text"),
        pytest.param("Hello", id="with_existing_text"),
    ],
)
def test_append_text_with_empty_string_does_nothing(document, existing_text):
    if existing_text:
        document.apply_append_text(existing_text)
        document.dirty = False
    document.apply_append_text("")
    assert document.text == existing_text
    assert not document.dirty


def test_each_document_has_unique_id():
    doc1 = Document()
    doc2 = Document()
    assert doc1.id != doc2.id
    assert isinstance(doc1.id, str)


def test_get_text_aggregates_children_when_not_dirty():
    from dockb.models.chapter import Chapter
    from dockb.models.paragraph import Paragraph
    from dockb.models.sentence import Sentence

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
    from dockb.models.chapter import Chapter
    from dockb.models.paragraph import Paragraph
    from dockb.models.sentence import Sentence

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


def test_set_text_with_delay_semantics(document):
    document.set_text("Hello", _delay_semantics=True)
    assert document.text == "Hello"
    assert document.dirty
