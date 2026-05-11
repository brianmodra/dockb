import pytest

from dockb.models.document import Document
from dockb.exceptions import EditTextRangeError


def test_apply_text_creates_the_text_and_invalidates_semantics():
    document = Document()
    document.apply_append_text("Hello World!")
    assert document.text == "Hello World!"
    assert document.dirty


def test_apply_text_appends_the_text_and_invalidates_semantics():
    document = Document()
    document.apply_append_text("Hello")
    document.apply_append_text(" World!")
    assert document.text == "Hello World!"
    assert document.dirty


def test_edit_text_does_replace_the_text_and_invalidates_semantics():
    document = Document()
    document.apply_append_text("Hello World!")
    document.dirty = False  # force it so we can test that it gets set to True
    document.apply_edit_text(6, 10, "Sir")
    assert document.text == "Hello Sir!"
    assert document.dirty


def test_edit_text_of_single_character_does_replace_the_text_and_invalidates_semantics():
    document = Document()
    document.apply_append_text("Hello World!")
    document.dirty = False  # force it so we can test that it gets set to True
    document.apply_edit_text(11, 11, ".")
    assert document.text == "Hello World."
    assert document.dirty


def test_edit_throws_if_end_is_before_start():
    document = Document()
    # make sure we are not just getting the exception because the start is wrong
    document.apply_append_text("Hello World!")
    with pytest.raises(EditTextRangeError):
        document.apply_edit_text(2, 1, "this won't work")


def test_edit_throws_if_start_is_out_of_range():
    document = Document()
    document.apply_append_text("Hello World!")
    with pytest.raises(EditTextRangeError):
        document.apply_edit_text(14, 14, "this won't work")


def test_edit_throws_if_end_is_out_of_range():
    document = Document()
    document.apply_append_text("Hello World!")
    with pytest.raises(EditTextRangeError):
        document.apply_edit_text(1, 15, "this won't work")


def test_edit_throws_if_start_is_out_of_range_with_no_existing_text():
    document = Document()
    with pytest.raises(EditTextRangeError):
        document.apply_edit_text(0, 0, "this won't work")


def test_edit_throws_if_start_is_negative():
    document = Document()
    document.apply_append_text("Hello World!")
    with pytest.raises(EditTextRangeError):
        document.apply_edit_text(-1, 5, "this won't work")


def test_edit_throws_if_end_is_negative():
    document = Document()
    document.apply_append_text("Hello World!")
    with pytest.raises(EditTextRangeError):
        document.apply_edit_text(1, -1, "this won't work")


def test_edit_text_with_empty_replacement_removes_text():
    document = Document()
    document.apply_append_text("Hello World!")
    document.dirty = False
    document.apply_edit_text(5, 10, "")
    assert document.text == "Hello!"
    assert document.dirty


def test_insert_text_at_beginning():
    document = Document()
    document.apply_append_text("World!")
    document.dirty = False
    document.apply_insert_text(0, "Hello ")
    assert document.text == "Hello World!"
    assert document.dirty


def test_insert_text_in_middle():
    document = Document()
    document.apply_append_text("Hello!")
    document.dirty = False
    document.apply_insert_text(5, " World")
    assert document.text == "Hello World!"
    assert document.dirty


def test_insert_text_at_end():
    document = Document()
    document.apply_append_text("Hello")
    document.dirty = False
    document.apply_insert_text(5, " World!")
    assert document.text == "Hello World!"
    assert document.dirty


def test_insert_text_into_empty_document_at_zero():
    document = Document()
    document.apply_insert_text(0, "Hello World!")
    assert document.text == "Hello World!"
    assert document.dirty


def test_insert_text_throws_if_pos_is_negative():
    document = Document()
    document.apply_append_text("Hello World!")
    with pytest.raises(EditTextRangeError):
        document.apply_insert_text(-1, "this won't work")


def test_insert_text_throws_if_pos_is_out_of_range():
    document = Document()
    document.apply_append_text("Hello World!")
    with pytest.raises(EditTextRangeError):
        document.apply_insert_text(14, "this won't work")


def test_insert_text_throws_if_pos_is_out_of_range_with_no_existing_text():
    document = Document()
    with pytest.raises(EditTextRangeError):
        document.apply_insert_text(1, "this won't work")


def test_insert_text_with_empty_text_does_nothing():
    document = Document()
    document.apply_append_text("Hello World!")
    document.dirty = False
    document.apply_insert_text(5, "")
    assert document.text == "Hello World!"
    assert not document.dirty


def test_insert_text_with_empty_text_into_empty_document_does_nothing():
    document = Document()
    document.apply_insert_text(0, "")
    assert document.text == ""
    assert not document.dirty


def test_append_text_with_empty_string_does_nothing():
    document = Document()
    document.apply_append_text("")
    assert document.text == ""
    assert not document.dirty


def test_append_text_with_empty_string_to_existing_text_does_nothing():
    document = Document()
    document.apply_append_text("Hello")
    document.dirty = False
    document.apply_append_text("")
    assert document.text == "Hello"
    assert not document.dirty


def test_each_document_has_unique_id():
    doc1 = Document()
    doc2 = Document()
    assert doc1.id != doc2.id
    assert isinstance(doc1.id, str)
