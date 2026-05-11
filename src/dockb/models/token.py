from __future__ import annotations
import string
from enum import Enum
from dockb.exceptions import TokenInvalidError
from .base import DockbModel


class TokenType(Enum):
    TOKEN_IS_UNDEFINED = "undefined"
    TOKEN_IS_WORD = "word"
    TOKEN_IS_PUNCTUATION = "punctuation"
    TOKEN_IS_WHITESPACE = "whitespace"
    TOKEN_IS_EXTENDED = "extended"

class Token(DockbModel):
    text: str = ""
    type: TokenType = TokenType.TOKEN_IS_UNDEFINED

    def get_text(self) -> str:
        return self.text

    def set_text(self, text: str) -> None:
        """
        Convert the text into either a word, punctuation, extended, or whitespace.

        When TOKEN_IS_WORD type, the text can be any combination of one or more alphanumeric characters.
        Letters include any Unicode letter (e.g. é, Ω, 汉), and digits include any Unicode digit.
        It can't contain punctuation, whitespace, or any other non-alpha-numeric characters.

        When TOKEN_IS_PUNCTUATION, the text must be exactly one character, and it must be a
        punctuation character. It cannot be whitespace or alphanumeric.
        A "punctuation character" is one of the characters defined in string.punctuation in the
        string library.

        When TOKEN_IS_EXTENDED, the text must be exactly one character, and it must be an
        extended non-alphabetic character, such as an emoji or symbol. It cannot be a letter,
        digit, punctuation, or whitespace.

        When TOKEN_IS_WHITESPACE, the text can be one or more characters of any combination
        of valid whitespace characters, i.e. any defined in string.whitespace.

        If the text parameter passed into this function is zero length, or does not conform to the above rules,
        then it will throw TokenInvalidError

        Note that TOKEN_IS_UNDEFINED is an initial state only, and cannot be set up using this
        function.
        """
        if not text:
            raise TokenInvalidError("text cannot be empty")

        if all(c in string.whitespace for c in text):
            self.text = text
            self.type = TokenType.TOKEN_IS_WHITESPACE
        elif len(text) == 1 and text in string.punctuation:
            self.text = text
            self.type = TokenType.TOKEN_IS_PUNCTUATION
        elif all(c.isalnum() for c in text):
            self.text = text
            self.type = TokenType.TOKEN_IS_WORD
        elif len(text) == 1 and not text[0].isalnum() and text[0] not in string.whitespace:
            self.text = text
            self.type = TokenType.TOKEN_IS_EXTENDED
        else:
            raise TokenInvalidError("text does not conform to any token type")

    def apply_edit_text(self, start: int, end: int, text: str) -> None:
        raise NotImplemented()

    def apply_append_text(self, text: str) -> None:
        raise NotImplemented()

    def apply_insert_text(self, pos: int, text: str) -> None:
        raise NotImplemented()
