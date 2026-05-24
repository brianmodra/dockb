"""Sentence model for tokenization and text reconstruction."""

from __future__ import annotations

from pydantic import Field

from dockb.models.token import Token

from .base import DockbModel


class Sentence(DockbModel):
    """
    A sentence is a list of Tokens (word, punctuation, whitespace, extended).
    Text is reconstructed by concatenating tokens in order.
    Tokenization converts text into Token objects.
    """

    tokens: list[Token] = Field(default_factory=list)
    text: str = ""

    def get_text(self) -> str:
        if self.dirty:
            return self.text
        if not self.tokens:
            return self.text
        return "".join(token.text + token.trailing_ws for token in self.tokens)

    def set_text(self, text: str) -> None:
        self.dirty = True
        self.text = text

    def clear_semantics(self) -> None:
        self.tokens.clear()
