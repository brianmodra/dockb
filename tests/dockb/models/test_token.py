import pytest

from dockb.exceptions import TokenInvalidError
from dockb.models.base import DataState
from dockb.models.token import POS, Token, Type
from dockb.models.utils.dockb_collection import InsertionMode


def test_initial_state_is_empty():
    token = Token()
    assert token.type == Type._
    assert token.text == ""


def test_set_text_as_word():
    token = Token()
    token.set_text("Hello")
    assert token.text == "Hello"
    assert token.type == Type.WORD


def test_set_text_as_number():
    token = Token()
    token.set_text("123")
    assert token.text == "123"
    assert token.type == Type.NUMBER
    assert token.is_digit


def test_set_text_as_float():
    token = Token()
    token.set_text("123.123")
    assert token.text == "123.123"
    assert token.type == Type.NUMBER
    assert not token.is_digit


def test_set_text_as_thousands():
    token = Token()
    token.set_text("123,123")
    assert token.text == "123,123"
    assert token.type == Type.NUMBER
    assert not token.is_digit


def test_set_text_with_multiple_dots():
    token = Token()
    token.set_text("123.123.3.12")
    assert token.text == "123.123.3.12"
    assert token.type == Type.NUMBER
    assert not token.is_digit


def test_set_text_with_multiple_commas():
    token = Token()
    token.set_text("123,123,3,12")
    assert token.text == "123,123,3,12"
    assert token.type == Type.NUMBER
    assert not token.is_digit


def test_categorizes_invalid_numbers():
    token = Token()
    token.set_text("123,,123,3,12")
    assert token.type == Type._
    token.set_text("123,,,3,12")
    assert token.type == Type._
    token.set_text("123,,,,3,12")
    assert token.type == Type._


def test_categorizes_invalid_dot_numbers():
    token = Token()
    token.set_text("123..1")
    assert token.type == Type._
    token.set_text("123...1")
    assert token.type == Type._
    token.set_text("123....1")
    assert token.type == Type._


def test_categorizes_mixed_dot_comma_numbers():
    token = Token()
    token.set_text("123.,.1")
    assert token.type == Type._
    token.set_text("123.,1")
    assert token.type == Type._
    token.set_text("123,.1")
    assert token.type == Type._


def test_set_text_as_word_with_number():
    token = Token()
    token.set_text("abc12")
    assert token.text == "abc12"
    assert token.type == Type.WORD


def test_set_text_as_word_with_leading_number():
    token = Token()
    token.set_text("123abc")
    assert token.text == "123abc"
    assert token.type == Type.WORD


def test_set_text_as_word_including_number():
    token = Token()
    token.set_text("x123abc")
    assert token.text == "x123abc"
    assert token.type == Type.WORD


def test_set_text_as_simple_word_with_number():
    token = Token()
    token.set_text("1a")
    assert token.text == "1a"
    assert token.type == Type.WORD


def test_categorizes_invalid_words_with_underscore():
    token = Token()
    token.set_text("abc_def")
    assert token.type == Type._
    token.set_text("abc_")
    assert token.type == Type._
    token.set_text("_def")
    assert token.type == Type._


def test_categorizes_invalid_words_with_embedded_or_leading_space():
    token = Token()
    token.set_text("abc def")
    assert token.type == Type._
    token.set_text(" abc")
    assert token.type == Type._


def test_sets_whitespace_set_text_as_word_with_trailing_space():
    token = Token()
    token.set_text("abc ")
    assert token.text == "abc"
    assert token.type == Type.WORD
    assert token.trailing_ws == " "


def test_throws_wnen_set_text_as_word_with_non_alphanum():
    token = Token()
    token.set_text("abc!")
    assert token.type == Type._


def test_categorizes_invalid_words_with_non_alphanum():
    token = Token()
    token.set_text("abc=")
    assert token.type == Type._
    token.set_text("ab$c")
    assert token.type == Type._
    token.set_text("a%bc")
    assert token.type == Type._
    token.set_text("!abc")
    assert token.type == Type._


def test_set_text_as_space():
    token = Token()
    token.set_text(" ")
    assert token.text == ""
    assert token.type == Type.WORD
    assert token.trailing_ws == " "


def test_set_text_with_newline():
    token = Token()
    token.set_text("Hello\n")
    assert token.text == "Hello"
    assert token.trailing_ws == "\n"
    assert token.type == Type.WORD


def test_set_text_with_tab():
    token = Token()
    token.set_text("Hello\t")
    assert token.text == "Hello"
    assert token.trailing_ws == "\t"
    assert token.type == Type.WORD


def test_set_text_with_multiple_whitespace():
    token = Token()
    token.set_text("Hello\t\n   \t \n")
    assert token.text == "Hello"
    assert token.trailing_ws == "\t\n   \t \n"
    assert token.type == Type.WORD


def test_set_text_as_comma():
    token = Token()
    token.set_text(",")
    assert token.text == ","
    assert token.type == Type.PUNCTUATION


def test_categorizes_invalid_punctuation():
    token = Token()
    token.set_text(",,")
    assert token.type == Type._
    token.set_text("..")
    assert token.type == Type._
    token.set_text(", ")
    assert token.type == Type._
    token.set_text("")
    assert token.type == Type._
    token.set_text("!!")
    assert token.type == Type._
    token.set_text(".?")
    assert token.type == Type._
    token.set_text("!@")
    assert token.type == Type._


def test_detects_ellipseis_if_set_text_as_three_full_stops():
    token = Token()
    token.set_text("...")
    assert token.text == "..."
    assert token.type == Type.PUNCTUATION


def test_adding_whitespace_to_a_word():
    token = Token()
    token.set_text("abc")
    token.set_trailing_ws("\n\n")
    assert token.text == "abc"
    assert token.trailing_ws == "\n\n"
    assert token.type == Type.WORD


def test_throws_when_adding_non_whitespace_to_a_word():
    token = Token()
    token.set_text("abc")
    with pytest.raises(TokenInvalidError):
        token.set_trailing_ws("\n,\n")


def test_categorizes_comma_and_space():
    token = Token()
    token.set_text(", ")
    assert token.type == Type._


def test_categorizes_empty_text():
    token = Token()
    token.set_text("")
    assert token.type == Type._


def test_set_text_as_various_punctuation():
    token = Token()
    for char in "!\"#$%&'()*+-./:;<=>?@[\\]^_`{|}~":
        token.set_text(char)
        assert token.text == char
        assert token.type == Type.PUNCTUATION


def test_categorizes_multiple_punctuation():
    token = Token()
    token.set_text("!!")
    assert token.type == Type._
    token.set_text(".?")
    assert token.type == Type._
    token.set_text("!@")
    assert token.type == Type._


def test_set_text_with_carriage_return():
    token = Token()
    token.set_text("Hello\r")
    assert token.text == "Hello"
    assert token.trailing_ws == "\r"
    assert token.type == Type.WORD


def test_set_text_with_form_feed():
    token = Token()
    token.set_text("Hello\f")
    assert token.text == "Hello"
    assert token.trailing_ws == "\f"
    assert token.type == Type.WORD


def test_set_text_with_vertical_tab():
    token = Token()
    token.set_text("Hello\v")
    assert token.text == "Hello"
    assert token.trailing_ws == "\v"
    assert token.type == Type.WORD


def test_categorizes_mixed_punctuation_and_word():
    token = Token()
    token.set_text("hello.")
    assert token.type == Type._
    token.set_text(".hello")
    assert token.type == Type._
    token.set_text("hel.lo")
    assert token.type == Type._


def test_categorizes_multi_char_extended():
    token = Token()
    token.set_text("🎉🎉")
    assert token.type == Type._


def test_set_text_as_extended_word():
    token = Token()
    token.set_text("café")
    assert token.text == "café"
    assert token.type == Type.WORD

    token.set_text("Ω")
    assert token.text == "Ω"
    assert token.type == Type.WORD

    token.set_text("é")
    assert token.text == "é"
    assert token.type == Type.WORD

    token.set_text("汉")
    assert token.text == "汉"
    assert token.type == Type.WORD


def test_set_text_as_extended_single_character():
    token = Token()
    token.set_text("🎉")
    assert token.text == "🎉"
    assert token.type == Type.EXTENDED

    token.set_text("★")
    assert token.text == "★"
    assert token.type == Type.EXTENDED


def test_each_token_has_unique_id():
    t1 = Token()
    t2 = Token()
    assert t1.id != t2.id
    assert isinstance(t1.id, str)


def test_set_pos_on_word():
    token = Token()
    token.set_text("Hello")
    token.set_pos("NOUN")
    assert token.pos == POS.NOUN


def test_set_pos_on_non_word():
    token = Token()
    token.set_text("!")
    token.set_pos("PUNCT")
    assert token.pos == POS.PUNCT

    token.set_text("123")
    token.set_pos("NUM")
    assert token.pos == POS.NUM


def test_sets_pos_on_inappropriate_types():
    token = Token()
    token.set_text("!")
    token.set_pos("PUNCT")
    assert token.pos == POS.PUNCT

    token.set_text("Hello")
    with pytest.raises(TokenInvalidError):
        token.set_pos("INVALID")


def test_set_lemma_on_non_word():
    token = Token()
    token.set_text("?")
    token.set_lemma("?")
    assert token.lemma == "?"

    token.set_text("123")
    token.set_lemma("123")
    assert token.lemma == "123"


def test_set_lemma_on_verb():
    token = Token()
    token.set_text("running")
    token.set_lemma("ran")
    assert token.lemma == "ran"
    token.set_text("runs")
    token.set_lemma("run")
    assert token.lemma == "run"
    token.set_text("was")
    token.set_lemma("be")
    assert token.lemma == "be"


def test_set_lemma_on_noun():
    token = Token()
    token.set_text("cats")
    token.set_lemma("cat")
    assert token.lemma == "cat"
    token.set_text("children")
    token.set_lemma("child")
    assert token.lemma == "child"
    # that's probably enough tests for lemma


@pytest.mark.parametrize(
    "text, expected_is_stop",
    [
        pytest.param("the", True, id="common_stop_word"),
        pytest.param("is", True, id="verb_stop_word"),
        pytest.param("hello", False, id="non_stop_word"),
        pytest.param("123", False, id="number_not_stop"),
        pytest.param("!", False, id="punctuation_not_stop"),
    ],
)
def test_is_stop_reflects_assignment(text, expected_is_stop):
    token = Token()
    token.set_text(text)
    token.is_stop = expected_is_stop
    assert token.is_stop == expected_is_stop


@pytest.mark.parametrize(
    "text, expected_like_num",
    [
        pytest.param("123", True, id="integer"),
        pytest.param("45.67", True, id="float"),
        pytest.param("one", False, id="word_text"),
        pytest.param("!", False, id="punctuation"),
    ],
)
def test_like_num_reflects_assignment(text, expected_like_num):
    token = Token()
    token.set_text(text)
    token.like_num = expected_like_num
    assert token.like_num == expected_like_num


@pytest.mark.parametrize(
    "text, expected_is_alpha",
    [
        pytest.param("hello", True, id="alphabetic_word"),
        pytest.param("123", False, id="numeric"),
        pytest.param("abc123", False, id="mixed_alphanumeric"),
        pytest.param("café", True, id="unicode_alpha"),
    ],
)
def test_is_alpha_reflects_assignment(text, expected_is_alpha):
    token = Token()
    token.set_text(text)
    token.is_alpha = expected_is_alpha
    assert token.is_alpha == expected_is_alpha


def test_clear_semantics_does_nothing(token):
    token.set_text("Hello")
    token.clear_semantics()
    assert token.text == "Hello"


def test_insert_child_raises_type_error(token):
    with pytest.raises(TypeError, match="Token has no children"):
        token.insert_child(Token(), InsertionMode.LAST)


def test_set_text_on_nothing_token_changes_state_to_new(token):
    assert token.state == DataState._
    token.set_text("Hello World")
    assert token.state == DataState.NEW


def test_set_text_on_new_token_leaves_states_as_new(token):
    token.set_text("Hello")  # make it NEW
    token.set_text("Hi")  # change it
    assert token.state == DataState.NEW


def test_set_text_on_sync_token_changes_state_to_changed(token):
    token.state = DataState.SYNC
    token.set_text("Hello")
    assert token.state == DataState.CHANGED
