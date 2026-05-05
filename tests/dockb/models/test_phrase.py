import pytest

from dockb.models.phrase import Phrase
from dockb.exceptions import EditTextRangeError


def test_apply_text_creates_the_text_and_invalidates_semantics():
    phrase = Phrase()
    phrase.apply_append_text("Hello World!")
    assert phrase.text == "Hello World!"
    assert phrase.dirty


def test_apply_text_appends_the_text_and_invalidates_semantics():
    phrase = Phrase()
    phrase.apply_append_text("Hello")
    phrase.apply_append_text(" World!")
    assert phrase.text == "Hello World!"
    assert phrase.dirty


def test_edit_text_does_replace_the_text_and_invalidates_semantics():
    phrase = Phrase()
    phrase.apply_append_text("Hello World!")
    phrase.dirty = False  # force it so we can test that it gets set to True
    phrase.apply_edit_text(6, 10, "Sir")
    assert phrase.text == "Hello Sir!"
    assert phrase.dirty


def test_edit_text_of_single_character_does_replace_the_text_and_invalidates_semantics():
    phrase = Phrase()
    phrase.apply_append_text("Hello World!")
    phrase.dirty = False  # force it so we can test that it gets set to True
    phrase.apply_edit_text(11, 11, ".")
    assert phrase.text == "Hello World."
    assert phrase.dirty


def test_edit_throws_if_end_is_before_start():
    phrase = Phrase()
    phrase.apply_append_text("Hello World!")
    with pytest.raises(EditTextRangeError):
        phrase.apply_edit_text(2, 1, "this won't work")


def test_edit_throws_if_start_is_out_of_range():
    phrase = Phrase()
    phrase.apply_append_text("Hello World!")
    with pytest.raises(EditTextRangeError):
        phrase.apply_edit_text(14, 14, "this won't work")


def test_edit_throws_if_end_is_out_of_range():
    phrase = Phrase()
    phrase.apply_append_text("Hello World!")
    with pytest.raises(EditTextRangeError):
        phrase.apply_edit_text(1, 15, "this won't work")


def test_edit_throws_if_start_is_out_of_range_with_no_existing_text():
    phrase = Phrase()
    with pytest.raises(EditTextRangeError):
        phrase.apply_edit_text(0, 0, "this won't work")


def test_edit_throws_if_start_is_negative():
    phrase = Phrase()
    phrase.apply_append_text("Hello World!")
    with pytest.raises(EditTextRangeError):
        phrase.apply_edit_text(-1, 5, "this won't work")


def test_edit_throws_if_end_is_negative():
    phrase = Phrase()
    phrase.apply_append_text("Hello World!")
    with pytest.raises(EditTextRangeError):
        phrase.apply_edit_text(1, -1, "this won't work")


def test_edit_text_with_empty_replacement_removes_text():
    phrase = Phrase()
    phrase.apply_append_text("Hello World!")
    phrase.dirty = False
    phrase.apply_edit_text(5, 10, "")
    assert phrase.text == "Hello!"
    assert phrase.dirty


def test_insert_text_at_beginning():
    phrase = Phrase()
    phrase.apply_append_text("World!")
    phrase.dirty = False
    phrase.apply_insert_text(0, "Hello ")
    assert phrase.text == "Hello World!"
    assert phrase.dirty


def test_insert_text_in_middle():
    phrase = Phrase()
    phrase.apply_append_text("Hello!")
    phrase.dirty = False
    phrase.apply_insert_text(5, " World")
    assert phrase.text == "Hello World!"
    assert phrase.dirty


def test_insert_text_at_end():
    phrase = Phrase()
    phrase.apply_append_text("Hello")
    phrase.dirty = False
    phrase.apply_insert_text(5, " World!")
    assert phrase.text == "Hello World!"
    assert phrase.dirty


def test_insert_text_into_empty_phrase_at_zero():
    phrase = Phrase()
    phrase.apply_insert_text(0, "Hello World!")
    assert phrase.text == "Hello World!"
    assert phrase.dirty


def test_insert_text_throws_if_pos_is_negative():
    phrase = Phrase()
    phrase.apply_append_text("Hello World!")
    with pytest.raises(EditTextRangeError):
        phrase.apply_insert_text(-1, "this won't work")


def test_insert_text_throws_if_pos_is_out_of_range():
    phrase = Phrase()
    phrase.apply_append_text("Hello World!")
    with pytest.raises(EditTextRangeError):
        phrase.apply_insert_text(14, "this won't work")


def test_insert_text_throws_if_pos_is_out_of_range_with_no_existing_text():
    phrase = Phrase()
    with pytest.raises(EditTextRangeError):
        phrase.apply_insert_text(1, "this won't work")


def test_insert_text_with_empty_text_does_nothing():
    phrase = Phrase()
    phrase.apply_append_text("Hello World!")
    phrase.dirty = False
    phrase.apply_insert_text(5, "")
    assert phrase.text == "Hello World!"
    assert not phrase.dirty


def test_insert_text_with_empty_text_into_empty_phrase_does_nothing():
    phrase = Phrase()
    phrase.apply_insert_text(0, "")
    assert phrase.text == ""
    assert not phrase.dirty


def test_append_text_with_empty_string_does_nothing():
    phrase = Phrase()
    phrase.apply_append_text("")
    assert phrase.text == ""
    assert not phrase.dirty


def test_append_text_with_empty_string_to_existing_text_does_nothing():
    phrase = Phrase()
    phrase.apply_append_text("Hello")
    phrase.dirty = False
    phrase.apply_append_text("")
    assert phrase.text == "Hello"
    assert not phrase.dirty
