import pytest

from dockb.models.token import Token, TokenType
from dockb.exceptions import TokenInvalidError


def test_initial_state_is_undefined():
    token = Token()
    assert token.type == TokenType.TOKEN_IS_UNDEFINED
    assert token.text == ""


def test_set_text_as_word():
    token = Token()
    token.set_text("Hello")
    assert token.text == "Hello"
    assert token.type == TokenType.TOKEN_IS_WORD


def test_set_text_as_number():
    token = Token()
    token.set_text("123")
    assert token.text == "123"
    assert token.type == TokenType.TOKEN_IS_WORD


def test_set_text_as_word_with_number():
    token = Token()
    token.set_text("abc12")
    assert token.text == "abc12"
    assert token.type == TokenType.TOKEN_IS_WORD


def test_set_text_as_word_with_leading_number():
    token = Token()
    token.set_text("123abc")
    assert token.text == "123abc"
    assert token.type == TokenType.TOKEN_IS_WORD


def test_set_text_as_word_including_number():
    token = Token()
    token.set_text("x123abc")
    assert token.text == "x123abc"
    assert token.type == TokenType.TOKEN_IS_WORD


def test_set_text_as_simple_word_with_number():
    token = Token()
    token.set_text("1a")
    assert token.text == "1a"
    assert token.type == TokenType.TOKEN_IS_WORD


def test_throws_wnen_set_text_as_word_with_underscore():
    token = Token()
    with pytest.raises(TokenInvalidError):
        token.set_text("abc_def")
    with pytest.raises(TokenInvalidError):
        token.set_text("abc_")
    with pytest.raises(TokenInvalidError):
        token.set_text("_def")


def test_throws_wnen_set_text_as_word_with_space():
    token = Token()
    with pytest.raises(TokenInvalidError):
        token.set_text("abc def")
    with pytest.raises(TokenInvalidError):
        token.set_text("abc ")
    with pytest.raises(TokenInvalidError):
        token.set_text(" abc")


def test_throws_wnen_set_text_as_word_with_non_alphanum():
    token = Token()
    with pytest.raises(TokenInvalidError):
        token.set_text("abc=")
    with pytest.raises(TokenInvalidError):
        token.set_text("ab$c")
    with pytest.raises(TokenInvalidError):
        token.set_text("a%bc")
    with pytest.raises(TokenInvalidError):
        token.set_text("!abc")


def test_set_text_as_space():
    token = Token()
    token.set_text(" ")
    assert token.text == " "
    assert token.type == TokenType.TOKEN_IS_WHITESPACE


def test_set_text_as_newline():
    token = Token()
    token.set_text("\n")
    assert token.text == "\n"
    assert token.type == TokenType.TOKEN_IS_WHITESPACE


def test_set_text_as_tab():
    token = Token()
    token.set_text("\t")
    assert token.text == "\t"
    assert token.type == TokenType.TOKEN_IS_WHITESPACE


def test_set_text_as_whitespace():
    token = Token()
    token.set_text("\t\n   \t \n")
    assert token.text == "\t\n   \t \n"
    assert token.type == TokenType.TOKEN_IS_WHITESPACE


def test_set_text_as_comma():
    token = Token()
    token.set_text(",")
    assert token.text == ","
    assert token.type == TokenType.TOKEN_IS_PUNCTUATION


def test_throws_if_set_text_as_commas():
    token = Token()
    with pytest.raises(TokenInvalidError):
        token.set_text(",,")


def test_throws_if_set_text_as_comma_and_space():
    token = Token()
    with pytest.raises(TokenInvalidError):
        token.set_text(", ")


def test_throws_if_set_text_is_empty():
    token = Token()
    with pytest.raises(TokenInvalidError):
        token.set_text("")


def test_set_text_as_various_punctuation():
    token = Token()
    for char in "!\"#$%&'()*+-./:;<=>?@[\\]^_`{|}~":
        token.set_text(char)
        assert token.text == char
        assert token.type == TokenType.TOKEN_IS_PUNCTUATION


def test_throws_if_set_text_is_multiple_punctuation():
    token = Token()
    with pytest.raises(TokenInvalidError):
        token.set_text("!!")
    with pytest.raises(TokenInvalidError):
        token.set_text(".?")
    with pytest.raises(TokenInvalidError):
        token.set_text("!@")


def test_set_text_as_carriage_return():
    token = Token()
    token.set_text("\r")
    assert token.text == "\r"
    assert token.type == TokenType.TOKEN_IS_WHITESPACE


def test_set_text_as_form_feed():
    token = Token()
    token.set_text("\f")
    assert token.text == "\f"
    assert token.type == TokenType.TOKEN_IS_WHITESPACE


def test_set_text_as_vertical_tab():
    token = Token()
    token.set_text("\v")
    assert token.text == "\v"
    assert token.type == TokenType.TOKEN_IS_WHITESPACE


def test_throws_if_set_text_mixed_whitespace_and_word():
    token = Token()
    with pytest.raises(TokenInvalidError):
        token.set_text("hello ")
    with pytest.raises(TokenInvalidError):
        token.set_text(" hello")
    with pytest.raises(TokenInvalidError):
        token.set_text("he llo")


def test_throws_if_set_text_mixed_punctuation_and_word():
    token = Token()
    with pytest.raises(TokenInvalidError):
        token.set_text("hello.")
    with pytest.raises(TokenInvalidError):
        token.set_text(".hello")
    with pytest.raises(TokenInvalidError):
        token.set_text("hel.lo")


def test_throws_if_set_text_is_multi_char_extended():
    token = Token()
    with pytest.raises(TokenInvalidError):
        token.set_text("🎉🎉")


def test_set_text_as_extended_word():
    token = Token()
    token.set_text("café")
    assert token.text == "café"
    assert token.type == TokenType.TOKEN_IS_WORD

    token.set_text("Ω")
    assert token.text == "Ω"
    assert token.type == TokenType.TOKEN_IS_WORD

    token.set_text("é")
    assert token.text == "é"
    assert token.type == TokenType.TOKEN_IS_WORD

    token.set_text("汉")
    assert token.text == "汉"
    assert token.type == TokenType.TOKEN_IS_WORD


def test_set_text_as_extended_single_character():
    token = Token()
    token.set_text("🎉")
    assert token.text == "🎉"
    assert token.type == TokenType.TOKEN_IS_EXTENDED

    token.set_text("★")
    assert token.text == "★"
    assert token.type == TokenType.TOKEN_IS_EXTENDED
