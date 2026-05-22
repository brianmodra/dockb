"""Sentence model for tokenization and text reconstruction."""

from __future__ import annotations

from pydantic import Field

from dockb.models.token import Token, TokenType
from dockb.models.utils.doc_cache import DocCache

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
        """
        Change the text.
        :param text:
        :param sentence_helper: either sync or async, calls tokenize indirectly
        :return:
        """
        self.dirty = True
        self.text = text

    def clear_semantics(self) -> None:
        self.tokens.clear()

    def tokenize(self, doc_cache: DocCache) -> None:
        """Tokenize the sentence text using spaCy via the provided doc_cache."""
        doc = doc_cache.get_doc(self.text)
        self.tokens = []
        for spacy_token in doc:
            token = Token()
            token.set_text(spacy_token.text)
            token.trailing_ws = spacy_token.whitespace_
            if token.type != TokenType.TOKEN_IS_EXTENDED:
                if spacy_token.pos_:
                    token.set_pos(spacy_token.pos_)
                token.set_lemma(spacy_token.lemma_)
            token.is_digit = spacy_token.is_digit
            token.like_num = spacy_token.like_num
            token.is_alpha = spacy_token.is_alpha
            self.tokens.append(token)
        self.dirty = False
