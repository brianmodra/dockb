import pytest
import spacy

from dockb.exceptions import EditTextRangeError
from dockb.models.sentence import Sentence
from dockb.models.token import POS, Token, Type
from dockb.services.semantics.doc_cache import DocCache
from dockb.services.semantics.sync_sentence_reconstructor import SyncSentenceReconstructor


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


def test_each_sentence_has_unique_id():
    s1 = Sentence()
    s2 = Sentence()
    assert s1.id != s2.id
    assert isinstance(s1.id, str)


def test_sentence_can_tokenise():
    nlp = spacy.load("en_core_web_sm")
    cache = DocCache(nlp)
    sentence_reconstructor = SyncSentenceReconstructor(cache)
    sentence = Sentence()
    sentence.set_text("The cat sat on the mat in the café looking at the dog 😜.")
    sentence_reconstructor.run(sentence)
    expected = [
        Token(text="The", type=Type.WORD, trailing_ws=" ", is_digit=False, like_num=False, is_alpha=True, lemma="the", pos=POS.DET),
        Token(text="cat", type=Type.WORD, trailing_ws=" ", is_digit=False, like_num=False, is_alpha=True, lemma="cat", pos=POS.NOUN),
        Token(text="sat", type=Type.WORD, trailing_ws=" ", is_digit=False, like_num=False, is_alpha=True, lemma="sit", pos=POS.VERB),
        Token(text="on", type=Type.WORD, trailing_ws=" ", is_digit=False, like_num=False, is_alpha=True, lemma="on", pos=POS.ADP),
        Token(text="the", type=Type.WORD, trailing_ws=" ", is_digit=False, like_num=False, is_alpha=True, lemma="the", pos=POS.DET),
        Token(text="mat", type=Type.WORD, trailing_ws=" ", is_digit=False, like_num=False, is_alpha=True, lemma="mat", pos=POS.NOUN),
        Token(text="in", type=Type.WORD, trailing_ws=" ", is_digit=False, like_num=False, is_alpha=True, lemma="in", pos=POS.ADP),
        Token(text="the", type=Type.WORD, trailing_ws=" ", is_digit=False, like_num=False, is_alpha=True, lemma="the", pos=POS.DET),
        Token(text="café", type=Type.WORD, trailing_ws=" ", is_digit=False, like_num=False, is_alpha=True, lemma="café", pos=POS.NOUN),
        Token(text="looking", type=Type.WORD, trailing_ws=" ", is_digit=False, like_num=False, is_alpha=True, lemma="look", pos=POS.VERB),
        Token(text="at", type=Type.WORD, trailing_ws=" ", is_digit=False, like_num=False, is_alpha=True, lemma="at", pos=POS.ADP),
        Token(text="the", type=Type.WORD, trailing_ws=" ", is_digit=False, like_num=False, is_alpha=True, lemma="the", pos=POS.DET),
        Token(text="dog", type=Type.WORD, trailing_ws=" ", is_digit=False, like_num=False, is_alpha=True, lemma="dog", pos=POS.NOUN),
        Token(text="😜", type=Type.EXTENDED, trailing_ws="", is_digit=False, like_num=False, is_alpha=False, lemma="", pos=POS._),
        Token(text=".", type=Type.PUNCTUATION, trailing_ws="", is_digit=False, like_num=False, is_alpha=False, lemma=".", pos=POS.PUNCT),
    ]
    print(sentence.tokens)
    assert len(sentence.tokens) == len(expected)
    for actual, exp in zip(sentence.tokens, expected):
        assert actual.text == exp.text
        assert actual.type == exp.type
        assert actual.trailing_ws == exp.trailing_ws
        assert actual.is_digit == exp.is_digit
        assert actual.like_num == exp.like_num
        assert actual.is_alpha == exp.is_alpha
        assert actual.lemma == exp.lemma
        assert actual.pos == exp.pos
    # async_sentence_reconstructor = AsyncSentenceReconstructor(doc_cache=)
