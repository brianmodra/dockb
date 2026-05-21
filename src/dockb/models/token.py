from __future__ import annotations

import string
from enum import Enum

from dockb.exceptions import TokenInvalidError

from .base import DockbModel


class POS(Enum):
    ADJ = "ADJ"
    ADP = "ADP"
    ADV = "ADV"
    AUX = "AUX"
    CONJ = "CONJ"
    CCONJ = "CCONJ"
    DET = "DET"
    INTJ = "INTJ"
    NOUN = "NOUN"
    NUM = "NUM"
    PART = "PART"
    PRON = "PRON"
    PROPN = "PROPN"
    PUNCT = "PUNCT"
    SCONJ = "SCONJ"
    SYM = "SYM"
    VERB = "VERB"
    X = "X"
    SPACE = "SPACE"
    _ = ""


class TokenType(Enum):
    TOKEN_IS_NUMBER = "number"
    TOKEN_IS_WORD = "word"
    TOKEN_IS_PUNCTUATION = "punctuation"
    TOKEN_IS_EXTENDED = "extended"
    _ = ""


class Token(DockbModel):
    text: str = ""
    type: TokenType = TokenType._
    trailing_ws: str = ""
    is_digit: bool = False
    like_num: bool = False
    is_alpha: bool = False
    is_stop: bool = False
    lemma: str = ""
    pos: POS = POS._

    def get_text(self) -> str:
        return self.text

    def set_text(self, text: str) -> None:
        """
        Convert the text into either a word, punctuation, extended, or whitespace.

        When TOKEN_IS_NUMBER type, the text can be any combination of one or more numeric characters.
        It can't contain punctuation, whitespace, or any other non-alpha-numeric characters, except
        a single decimal point surrounded by numbers, or a single comma surrounded by numbers.
        e.g. 1.234 is a number, 1.2.3 is also, 1,234 is a number, so is 1,2,3 or 1,23,4
        But 1..2 is not, and 1,,2 is not.

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

        If the text parameter passed into this function is zero length, or does not conform to the above rules,
        then it will be an uncategrorised TokenType._
        """

        # initialise everything
        self.text = ""
        self.type = TokenType._
        self.trailing_ws: str = ""
        self.is_digit = False
        self.like_num = False
        self.is_alpha = False
        self.is_stop = False
        self.lemma = ""
        self.pos = POS._

        if not text:
            # text cannot be empty
            return

        # Extract trailing whitespace
        trailing = ""
        for i in range(len(text) - 1, -1, -1):
            if text[i] in string.whitespace:
                trailing = text[i] + trailing
            else:
                break
        core = text[: len(text) - len(trailing)]

        # Whitespace-only token becomes an empty word with trailing_ws
        if not core:
            self.text = ""
            self.trailing_ws = text
            self.type = TokenType.TOKEN_IS_WORD
            self.is_digit = False
        elif self._is_number(core):
            self.text = core
            self.trailing_ws = trailing
            self.type = TokenType.TOKEN_IS_NUMBER
            self.is_digit = core.isdigit()
        elif core in string.punctuation or core == "...":
            if trailing:
                # punctuation cannot have trailing whitespace
                self.type = TokenType._
                self.trailing_ws = trailing
            else:
                self.type = TokenType.TOKEN_IS_PUNCTUATION
                self.trailing_ws = ""
            self.text = core
            self.is_digit = False
        elif core and all(c.isalnum() for c in core):
            self.text = core
            self.trailing_ws = trailing
            self.type = TokenType.TOKEN_IS_WORD
            self.is_digit = False
        elif (
            len(core) == 1
            and not core[0].isalnum()
            and core[0] not in string.whitespace
        ):
            if trailing:
                # extended character cannot have trailing whitespace
                self.trailing_ws = trailing
                self.type = TokenType._
            else:
                self.trailing_ws = ""
                self.type = TokenType.TOKEN_IS_EXTENDED
            self.text = core
            self.is_digit = False
        else:
            # text does not conform to any token type
            self.type = TokenType._
            self.text = core

    def _is_number(self, text: str) -> bool:
        if not text:
            return False
        if text.isdigit():
            return True
        if ".." in text or ",," in text:
            return False
        if "." in text and "," in text:
            return False
        if all(c.isdigit() or c in ".," for c in text) and text[0].isdigit() and text[-1].isdigit():
            return True
        return False

    def set_pos(self, pos: str | POS) -> None:
        if isinstance(pos, POS):
            pos_enum = pos
        else:
            try:
                pos_enum = POS(pos)
            except ValueError:
                raise TokenInvalidError(f"'{pos}' is not a valid POS tag")
        self.pos = pos_enum

    def set_lemma(self, lemma: str) -> None:
        self.lemma = lemma

    def set_trailing_ws(self, trailing_ws: str) -> None:
        """
        Set the trailing whitespace for this token.

        The provided string must contain only valid whitespace characters as
        defined in string.whitespace. If it contains any non-whitespace characters,
        TokenInvalidError is raised.
        """
        if not all(c in string.whitespace for c in trailing_ws):
            raise TokenInvalidError(
                "trailing_ws must contain only valid whitespace characters"
            )
        self.trailing_ws = trailing_ws

    def apply_edit_text(self, start: int, end: int, text: str) -> None:
        raise NotImplemented()

    def apply_append_text(self, text: str) -> None:
        raise NotImplemented()

    def apply_insert_text(self, pos: int, text: str) -> None:
        raise NotImplemented()
