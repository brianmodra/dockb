"""Tokenizes sentence text into Token objects using spaCy."""

import threading

from dockb.models.token import Token, Type
from dockb.services.semantics.doc_cache import DocCache


class TokenizationCancelled(Exception):
    """Raised when tokenization is interrupted by a cancellation request."""


class SentenceTokenizer:
    """Converts raw sentence text into a list of Token objects via spaCy."""

    def __init__(self) -> None:
        self._cancel_event = threading.Event()

    def cancel(self) -> None:
        """Signal the tokenizer to stop as soon as it is safe."""
        self._cancel_event.set()

    def tokenize(self, text: str, doc_cache: DocCache) -> list[Token]:
        """Tokenize the given text using spaCy via the provided doc_cache.

        Returns a list of Token objects with POS, lemma, and whitespace data.
        Raises TokenizationCancelled if cancel() was called during processing.
        """
        if self._cancel_event.is_set():
            raise TokenizationCancelled()

        doc = doc_cache.get_doc(text)

        tokens: list[Token] = []
        for spacy_token in doc:
            if self._cancel_event.is_set():
                raise TokenizationCancelled()

            token = Token()
            token.set_text(spacy_token.text)
            token.trailing_ws = spacy_token.whitespace_
            if token.type != Type.EXTENDED:
                if spacy_token.pos_:
                    token.set_pos(spacy_token.pos_)
                token.set_lemma(spacy_token.lemma_)
            token.is_digit = spacy_token.is_digit
            token.like_num = spacy_token.like_num
            token.is_alpha = spacy_token.is_alpha
            tokens.append(token)
        return tokens
