import pytest

from dockb.models.sentence import Sentence
from dockb.exceptions import EditTextRangeError


def test_apply_text_creates_the_text_and_invalidates_semantics():
    sentence = Sentence()
    sentence.apply_append_text("Hello World!")
    assert sentence.text == "Hello World!"
    assert sentence.dirty


def test_apply_text_appends_the_text_and_invalidates_semantics():
    sentence = Sentence()
    sentence.apply_append_text("Hello")
    sentence.apply_append_text(" World!")
    assert sentence.text == "Hello World!"
    assert sentence.dirty


def test_edit_text_does_replace_the_text_and_invalidates_semantics():
    sentence = Sentence()
    sentence.apply_append_text("Hello World!")
    sentence.dirty = False  # force it so we can test that it gets set to True
    sentence.apply_edit_text(6, 10, "Sir")
    assert sentence.text == "Hello Sir!"
    assert sentence.dirty


def test_edit_text_of_single_character_does_replace_the_text_and_invalidates_semantics():
    sentence = Sentence()
    sentence.apply_append_text("Hello World!")
    sentence.dirty = False  # force it so we can test that it gets set to True
    sentence.apply_edit_text(11, 11, ".")
    assert sentence.text == "Hello World."
    assert sentence.dirty


def test_edit_throws_if_end_is_before_start():
    sentence = Sentence()
    sentence.apply_append_text("Hello World!")
    with pytest.raises(EditTextRangeError):
        sentence.apply_edit_text(2, 1, "this won't work")


def test_edit_throws_if_start_is_out_of_range():
    sentence = Sentence()
    sentence.apply_append_text("Hello World!")
    with pytest.raises(EditTextRangeError):
        sentence.apply_edit_text(14, 14, "this won't work")


def test_edit_throws_if_end_is_out_of_range():
    sentence = Sentence()
    sentence.apply_append_text("Hello World!")
    with pytest.raises(EditTextRangeError):
        sentence.apply_edit_text(1, 15, "this won't work")


def test_edit_throws_if_start_is_out_of_range_with_no_existing_text():
    sentence = Sentence()
    with pytest.raises(EditTextRangeError):
        sentence.apply_edit_text(0, 0, "this won't work")


def test_edit_throws_if_start_is_negative():
    sentence = Sentence()
    sentence.apply_append_text("Hello World!")
    with pytest.raises(EditTextRangeError):
        sentence.apply_edit_text(-1, 5, "this won't work")


def test_edit_throws_if_end_is_negative():
    sentence = Sentence()
    sentence.apply_append_text("Hello World!")
    with pytest.raises(EditTextRangeError):
        sentence.apply_edit_text(1, -1, "this won't work")


def test_edit_text_with_empty_replacement_removes_text():
    sentence = Sentence()
    sentence.apply_append_text("Hello World!")
    sentence.dirty = False
    sentence.apply_edit_text(5, 10, "")
    assert sentence.text == "Hello!"
    assert sentence.dirty


def test_insert_text_at_beginning():
    sentence = Sentence()
    sentence.apply_append_text("World!")
    sentence.dirty = False
    sentence.apply_insert_text(0, "Hello ")
    assert sentence.text == "Hello World!"
    assert sentence.dirty


def test_insert_text_in_middle():
    sentence = Sentence()
    sentence.apply_append_text("Hello!")
    sentence.dirty = False
    sentence.apply_insert_text(5, " World")
    assert sentence.text == "Hello World!"
    assert sentence.dirty


def test_insert_text_at_end():
    sentence = Sentence()
    sentence.apply_append_text("Hello")
    sentence.dirty = False
    sentence.apply_insert_text(5, " World!")
    assert sentence.text == "Hello World!"
    assert sentence.dirty


def test_insert_text_into_empty_sentence_at_zero():
    sentence = Sentence()
    sentence.apply_insert_text(0, "Hello World!")
    assert sentence.text == "Hello World!"
    assert sentence.dirty


def test_insert_text_throws_if_pos_is_negative():
    sentence = Sentence()
    sentence.apply_append_text("Hello World!")
    with pytest.raises(EditTextRangeError):
        sentence.apply_insert_text(-1, "this won't work")


def test_insert_text_throws_if_pos_is_out_of_range():
    sentence = Sentence()
    sentence.apply_append_text("Hello World!")
    with pytest.raises(EditTextRangeError):
        sentence.apply_insert_text(14, "this won't work")


def test_insert_text_throws_if_pos_is_out_of_range_with_no_existing_text():
    sentence = Sentence()
    with pytest.raises(EditTextRangeError):
        sentence.apply_insert_text(1, "this won't work")


def test_insert_text_with_empty_text_does_nothing():
    sentence = Sentence()
    sentence.apply_append_text("Hello World!")
    sentence.dirty = False
    sentence.apply_insert_text(5, "")
    assert sentence.text == "Hello World!"
    assert not sentence.dirty


def test_insert_text_with_empty_text_into_empty_sentence_does_nothing():
    sentence = Sentence()
    sentence.apply_insert_text(0, "")
    assert sentence.text == ""
    assert not sentence.dirty


def test_append_text_with_empty_string_does_nothing():
    sentence = Sentence()
    sentence.apply_append_text("")
    assert sentence.text == ""
    assert not sentence.dirty


def test_append_text_with_empty_string_to_existing_text_does_nothing():
    sentence = Sentence()
    sentence.apply_append_text("Hello")
    sentence.dirty = False
    sentence.apply_append_text("")
    assert sentence.text == "Hello"
    assert not sentence.dirty
