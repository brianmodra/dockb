import pytest

from dockb.models import Paragraph
from dockb.exceptions import EditTextRangeError


def test_apply_text_creates_the_text_and_invalidates_semantics():
    paragraph = Paragraph()
    paragraph.apply_append_text("Hello World!")
    assert paragraph.text == "Hello World!"
    assert paragraph.dirty


def test_apply_text_appends_the_text_and_invalidates_semantics():
    paragraph = Paragraph()
    paragraph.apply_append_text("Hello")
    paragraph.apply_append_text(" World!")
    assert paragraph.text == "Hello World!"
    assert paragraph.dirty


def test_edit_text_does_replace_the_text_and_invalidates_semantics():
    paragraph = Paragraph()
    paragraph.apply_append_text("Hello World!")
    paragraph.dirty = False  # force it so we can test that it gets set to True
    paragraph.apply_edit_text(6, 10, "Sir")
    assert paragraph.text == "Hello Sir!"
    assert paragraph.dirty


def test_edit_text_of_single_character_does_replace_the_text_and_invalidates_semantics():
    paragraph = Paragraph()
    paragraph.apply_append_text("Hello World!")
    paragraph.dirty = False  # force it so we can test that it gets set to True
    paragraph.apply_edit_text(11, 11, ".")
    assert paragraph.text == "Hello World."
    assert paragraph.dirty


def test_edit_throws_if_end_is_before_start():
    paragraph = Paragraph()
    paragraph.apply_append_text("Hello World!")
    with pytest.raises(EditTextRangeError):
        paragraph.apply_edit_text(2, 1, "this won't work")


def test_edit_throws_if_start_is_out_of_range():
    paragraph = Paragraph()
    paragraph.apply_append_text("Hello World!")
    with pytest.raises(EditTextRangeError):
        paragraph.apply_edit_text(14, 14, "this won't work")


def test_edit_throws_if_end_is_out_of_range():
    paragraph = Paragraph()
    paragraph.apply_append_text("Hello World!")
    with pytest.raises(EditTextRangeError):
        paragraph.apply_edit_text(1, 15, "this won't work")


def test_edit_throws_if_start_is_out_of_range_with_no_existing_text():
    paragraph = Paragraph()
    with pytest.raises(EditTextRangeError):
        paragraph.apply_edit_text(0, 0, "this won't work")


def test_edit_throws_if_start_is_negative():
    paragraph = Paragraph()
    paragraph.apply_append_text("Hello World!")
    with pytest.raises(EditTextRangeError):
        paragraph.apply_edit_text(-1, 5, "this won't work")


def test_edit_throws_if_end_is_negative():
    paragraph = Paragraph()
    paragraph.apply_append_text("Hello World!")
    with pytest.raises(EditTextRangeError):
        paragraph.apply_edit_text(1, -1, "this won't work")


def test_edit_text_with_empty_replacement_removes_text():
    paragraph = Paragraph()
    paragraph.apply_append_text("Hello World!")
    paragraph.dirty = False
    paragraph.apply_edit_text(5, 10, "")
    assert paragraph.text == "Hello!"
    assert paragraph.dirty


def test_insert_text_at_beginning():
    paragraph = Paragraph()
    paragraph.apply_append_text("World!")
    paragraph.dirty = False
    paragraph.apply_insert_text(0, "Hello ")
    assert paragraph.text == "Hello World!"
    assert paragraph.dirty


def test_insert_text_in_middle():
    paragraph = Paragraph()
    paragraph.apply_append_text("Hello!")
    paragraph.dirty = False
    paragraph.apply_insert_text(5, " World")
    assert paragraph.text == "Hello World!"
    assert paragraph.dirty


def test_insert_text_at_end():
    paragraph = Paragraph()
    paragraph.apply_append_text("Hello")
    paragraph.dirty = False
    paragraph.apply_insert_text(5, " World!")
    assert paragraph.text == "Hello World!"
    assert paragraph.dirty


def test_insert_text_into_empty_paragraph_at_zero():
    paragraph = Paragraph()
    paragraph.apply_insert_text(0, "Hello World!")
    assert paragraph.text == "Hello World!"
    assert paragraph.dirty


def test_insert_text_throws_if_pos_is_negative():
    paragraph = Paragraph()
    paragraph.apply_append_text("Hello World!")
    with pytest.raises(EditTextRangeError):
        paragraph.apply_insert_text(-1, "this won't work")


def test_insert_text_throws_if_pos_is_out_of_range():
    paragraph = Paragraph()
    paragraph.apply_append_text("Hello World!")
    with pytest.raises(EditTextRangeError):
        paragraph.apply_insert_text(14, "this won't work")


def test_insert_text_throws_if_pos_is_out_of_range_with_no_existing_text():
    paragraph = Paragraph()
    with pytest.raises(EditTextRangeError):
        paragraph.apply_insert_text(1, "this won't work")


def test_insert_text_with_empty_text_does_nothing():
    paragraph = Paragraph()
    paragraph.apply_append_text("Hello World!")
    paragraph.dirty = False
    paragraph.apply_insert_text(5, "")
    assert paragraph.text == "Hello World!"
    assert not paragraph.dirty


def test_insert_text_with_empty_text_into_empty_paragraph_does_nothing():
    paragraph = Paragraph()
    paragraph.apply_insert_text(0, "")
    assert paragraph.text == ""
    assert not paragraph.dirty


def test_append_text_with_empty_string_does_nothing():
    paragraph = Paragraph()
    paragraph.apply_append_text("")
    assert paragraph.text == ""
    assert not paragraph.dirty


def test_append_text_with_empty_string_to_existing_text_does_nothing():
    paragraph = Paragraph()
    paragraph.apply_append_text("Hello")
    paragraph.dirty = False
    paragraph.apply_append_text("")
    assert paragraph.text == "Hello"
    assert not paragraph.dirty


def test_each_paragraph_has_unique_id():
    p1 = Paragraph()
    p2 = Paragraph()
    assert p1.id != p2.id
    assert isinstance(p1.id, str)
