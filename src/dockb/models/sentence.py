"""Sentence model for tokenization and text reconstruction."""

from __future__ import annotations

from pydantic import Field

from dockb.models.token import Token
from dockb.models.utils.dockb_collection import DockbCollection, DockbModelBase, InsertionMode

from .base import DockbModel


class Sentence(DockbModel):
    """
    A sentence is a list of Tokens (word, punctuation, whitespace, extended).
    Text is reconstructed by concatenating tokens in order.
    Tokenization converts text into Token objects.
    """

    tokens: DockbCollection[Token] = Field(default_factory=DockbCollection)

    def get_text(self) -> str:
        if self.dirty:
            return self.text
        if not self.tokens:
            return self.text
        return "".join(token.text + token.trailing_ws for token in self.tokens)

    def clear_semantics(self) -> None:
        self.tokens.clear()

    def delete_child(self, child_id: str) -> bool:
        return self.tokens.delete(child_id)

    def insert_child(self, child: DockbModelBase, insertion_mode: InsertionMode, after: str | None = None) -> None:
        if not isinstance(child, Token):
            raise TypeError(f"Expected Token, got {type(child).__name__}")
        self.tokens.insert(child, insertion_mode, after)
