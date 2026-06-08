"""Token model with POS tags, lemmas, and text classification."""

from __future__ import annotations

import string
from enum import Enum

from dockb.exceptions import TokenInvalidError
from dockb.models.utils.dockb_collection import DockbModelBase, InsertionMode

from .base import DockbModel


class POS(Enum):
    """Part-of-speech tags from the Universal Dependencies framework."""

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


class Type(Enum):
    """Classification of token text content."""

    NUMBER = "number"
    WORD = "word"
    PUNCTUATION = "punctuation"
    EXTENDED = "extended"
    _ = ""


class Token(DockbModel):  # pylint: disable=too-many-instance-attributes
    """A single token with text, type, POS tag, and linguistic attributes."""

    type: Type = Type._
    trailing_ws: str = ""
    is_digit: bool = False
    like_num: bool = False
    is_alpha: bool = False
    is_stop: bool = False
    lemma: str = ""
    pos: POS = POS._

    def get_text(self) -> str:
        return self.text

    def set_text(self, text: str) -> None:  # noqa: C901  # pylint: disable=too-many-branches,too-many-statements
        """
        Convert the text into either a word, punctuation, extended, or whitespace.

        NUMBER: one or more numeric characters. May contain a single
        decimal point or comma surrounded by numbers (e.g. 1.234, 1,234).
        Cannot contain punctuation, whitespace, or non-numeric characters.

        WORD: one or more alphanumeric characters including Unicode
        letters and digits. Cannot contain punctuation or whitespace.

        PUNCTUATION: exactly one punctuation character from
        string.punctuation. Cannot be whitespace or alphanumeric.

        EXTENDED: exactly one extended non-alphabetic character
        (e.g. emoji or symbol). Cannot be letter, digit, punctuation, or whitespace.

        Non-conforming or empty text becomes Type._
        """

        # initialize everything
        self.text = ""
        self.type = Type._
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
            self.type = Type.WORD
            self.is_digit = False
        elif self._is_number(core):
            self.text = core
            self.trailing_ws = trailing
            self.type = Type.NUMBER
            self.is_digit = core.isdigit()
        elif core in string.punctuation or core == "...":
            if trailing:
                # Punctuation cannot have trailing whitespace
                self.type = Type._
                self.trailing_ws = trailing
            else:
                self.type = Type.PUNCTUATION
                self.trailing_ws = ""
            self.text = core
            self.is_digit = False
        elif core and all(c.isalnum() for c in core):
            self.text = core
            self.trailing_ws = trailing
            self.type = Type.WORD
            self.is_digit = False
        elif len(core) == 1 and not core[0].isalnum() and core[0] not in string.whitespace:
            if trailing:
                # Extended character cannot have trailing whitespace
                self.trailing_ws = trailing
                self.type = Type._
            else:
                self.trailing_ws = ""
                self.type = Type.EXTENDED
            self.text = core
            self.is_digit = False
        else:
            # Text does not conform to any token type
            self.type = Type._
            self.text = core


        self.on_changed()

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
        """Set the part-of-speech tag, validating against the POS enum."""
        if isinstance(pos, POS):
            pos_enum = pos
        else:
            try:
                pos_enum = POS(pos)
            except ValueError as exc:
                raise TokenInvalidError(f"'{pos}' is not a valid POS tag") from exc
        self.pos = pos_enum

    def set_lemma(self, lemma: str) -> None:
        """Set the lemmatized form of the token text."""
        self.lemma = lemma

    def set_trailing_ws(self, trailing_ws: str) -> None:
        """
        Set the trailing whitespace for this token.

        The provided string must contain only valid whitespace characters as
        defined in string.whitespace. If it contains any non-whitespace characters,
        TokenInvalidError is raised.
        """
        if not all(c in string.whitespace for c in trailing_ws):
            raise TokenInvalidError("trailing_ws must contain only valid whitespace characters")
        self.trailing_ws = trailing_ws

    def clear_semantics(self) -> None:
        pass

    def delete_child(self, child_id: str) -> bool:
        return False

    def insert_child(self, child: DockbModelBase, insertion_mode: InsertionMode, after: str | None = None) -> None:
        raise TypeError("Token has no children")
