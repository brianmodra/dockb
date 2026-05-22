import pytest

from dockb.exceptions import TokenInvalidError
from dockb.models.token import POS, Token, Type


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
    assert token.is_digit == True


def test_set_text_as_float():
    token = Token()
    token.set_text("123.123")
    assert token.text == "123.123"
    assert token.type == Type.NUMBER
    assert token.is_digit == False


def test_set_text_as_thousands():
    token = Token()
    token.set_text("123,123")
    assert token.text == "123,123"
    assert token.type == Type.NUMBER
    assert token.is_digit == False


def test_set_text_with_multiple_dots():
    token = Token()
    token.set_text("123.123.3.12")
    assert token.text == "123.123.3.12"
    assert token.type == Type.NUMBER
    assert token.is_digit == False


def test_set_text_with_multiple_commas():
    token = Token()
    token.set_text("123,123,3,12")
    assert token.text == "123,123,3,12"
    assert token.type == Type.NUMBER
    assert token.is_digit == False


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
