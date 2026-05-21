import pytest

from dockb.models import Chapter
from dockb.exceptions import EditTextRangeError


def test_apply_text_creates_the_text_and_invalidates_semantics():
    chapter = Chapter()
    chapter.apply_append_text("Hello World!")
    assert chapter.text == "Hello World!"
    assert chapter.dirty


def test_apply_text_appends_the_text_and_invalidates_semantics():
    chapter = Chapter()
    chapter.apply_append_text("Hello")
    chapter.apply_append_text(" World!")
    assert chapter.text == "Hello World!"
    assert chapter.dirty


def test_edit_text_does_replace_the_text_and_invalidates_semantics():
    chapter = Chapter()
    chapter.apply_append_text("Hello World!")
    chapter.dirty = False  # force it so we can test that it gets set to True
    chapter.apply_edit_text(6, 10, "Sir")
    assert chapter.text == "Hello Sir!"
    assert chapter.dirty


def test_edit_text_of_single_character_does_replace_the_text_and_invalidates_semantics():
    chapter = Chapter()
    chapter.apply_append_text("Hello World!")
    chapter.dirty = False  # force it so we can test that it gets set to True
    chapter.apply_edit_text(11, 11, ".")
    assert chapter.text == "Hello World."
    assert chapter.dirty


def test_edit_throws_if_end_is_before_start():
    chapter = Chapter()
    chapter.apply_append_text("Hello World!")
    with pytest.raises(EditTextRangeError):
        chapter.apply_edit_text(2, 1, "this won't work")


def test_edit_throws_if_start_is_out_of_range():
    chapter = Chapter()
    chapter.apply_append_text("Hello World!")
    with pytest.raises(EditTextRangeError):
        chapter.apply_edit_text(14, 14, "this won't work")


def test_edit_throws_if_end_is_out_of_range():
    chapter = Chapter()
    chapter.apply_append_text("Hello World!")
    with pytest.raises(EditTextRangeError):
        chapter.apply_edit_text(1, 15, "this won't work")


def test_edit_throws_if_start_is_out_of_range_with_no_existing_text():
    chapter = Chapter()
    with pytest.raises(EditTextRangeError):
        chapter.apply_edit_text(0, 0, "this won't work")


def test_edit_throws_if_start_is_negative():
    chapter = Chapter()
    chapter.apply_append_text("Hello World!")
    with pytest.raises(EditTextRangeError):
        chapter.apply_edit_text(-1, 5, "this won't work")


def test_edit_throws_if_end_is_negative():
    chapter = Chapter()
    chapter.apply_append_text("Hello World!")
    with pytest.raises(EditTextRangeError):
        chapter.apply_edit_text(1, -1, "this won't work")


def test_edit_text_with_empty_replacement_removes_text():
    chapter = Chapter()
    chapter.apply_append_text("Hello World!")
    chapter.dirty = False
    chapter.apply_edit_text(5, 10, "")
    assert chapter.text == "Hello!"
    assert chapter.dirty


def test_insert_text_at_beginning():
    chapter = Chapter()
    chapter.apply_append_text("World!")
    chapter.dirty = False
    chapter.apply_insert_text(0, "Hello ")
    assert chapter.text == "Hello World!"
    assert chapter.dirty


def test_insert_text_in_middle():
    chapter = Chapter()
    chapter.apply_append_text("Hello!")
    chapter.dirty = False
    chapter.apply_insert_text(5, " World")
    assert chapter.text == "Hello World!"
    assert chapter.dirty


def test_insert_text_at_end():
    chapter = Chapter()
    chapter.apply_append_text("Hello")
    chapter.dirty = False
    chapter.apply_insert_text(5, " World!")
    assert chapter.text == "Hello World!"
    assert chapter.dirty


def test_insert_text_into_empty_chapter_at_zero():
    chapter = Chapter()
    chapter.apply_insert_text(0, "Hello World!")
    assert chapter.text == "Hello World!"
    assert chapter.dirty


def test_insert_text_throws_if_pos_is_negative():
    chapter = Chapter()
    chapter.apply_append_text("Hello World!")
    with pytest.raises(EditTextRangeError):
        chapter.apply_insert_text(-1, "this won't work")


def test_insert_text_throws_if_pos_is_out_of_range():
    chapter = Chapter()
    chapter.apply_append_text("Hello World!")
    with pytest.raises(EditTextRangeError):
        chapter.apply_insert_text(14, "this won't work")


def test_insert_text_throws_if_pos_is_out_of_range_with_no_existing_text():
    chapter = Chapter()
    with pytest.raises(EditTextRangeError):
        chapter.apply_insert_text(1, "this won't work")


def test_insert_text_with_empty_text_does_nothing():
    chapter = Chapter()
    chapter.apply_append_text("Hello World!")
    chapter.dirty = False
    chapter.apply_insert_text(5, "")
    assert chapter.text == "Hello World!"
    assert not chapter.dirty


def test_insert_text_with_empty_text_into_empty_chapter_does_nothing():
    chapter = Chapter()
    chapter.apply_insert_text(0, "")
    assert chapter.text == ""
    assert not chapter.dirty


def test_append_text_with_empty_string_does_nothing():
    chapter = Chapter()
    chapter.apply_append_text("")
    assert chapter.text == ""
    assert not chapter.dirty


def test_append_text_with_empty_string_to_existing_text_does_nothing():
    chapter = Chapter()
    chapter.apply_append_text("Hello")
    chapter.dirty = False
    chapter.apply_append_text("")
    assert chapter.text == "Hello"
    assert not chapter.dirty


def test_each_chapter_has_unique_id():
    ch1 = Chapter()
    ch2 = Chapter()
    assert ch1.id != ch2.id
    assert isinstance(ch1.id, str)
