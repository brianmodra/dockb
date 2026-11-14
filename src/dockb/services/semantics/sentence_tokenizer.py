"""Tokenizes sentence text into Token objects using spaCy."""

import threading
from collections.abc import Sequence

from spacy.tokens import Doc, Span

from dockb.models.formatting import FormatRun
from dockb.models.token import Token, Type
from dockb.services.semantics.doc_cache import DocCache


class TokenizationCancelled(Exception):
    """Raised when tokenization is interrupted by a cancellation request."""


def apply_format_runs(tokens: list[Token], runs: Sequence[FormatRun]) -> None:
    """Apply whole-token formatting from *runs* to *tokens*.

    A run touching any part of a token — including its trailing whitespace —
    formats the whole token. Runs may not overlap, so at most one applies.
    """
    position = 0
    for token in tokens:
        token_start = position
        token_end = position + len(token.text) + len(token.trailing_ws)
        position = token_end
        for run in runs:
            if run.start < token_end and run.end > token_start:
                token.style = run.style
                token.weight = run.weight
                token.family = run.family
                token.size = run.size
                break


class SentenceTokenizer:
    """Converts raw sentence text into a list of Token objects via spaCy."""

    def __init__(self) -> None:
        self._cancel_event = threading.Event()

    def cancel(self) -> None:
        """Signal the tokenizer to stop as soon as it is safe."""
        self._cancel_event.set()

    def tokenize(
        self,
        text: str,
        doc_cache: DocCache,
        format_runs: Sequence[FormatRun] = (),
    ) -> list[Token]:
        """Tokenize the given text using spaCy via the provided doc_cache.

        Returns a list of Token objects with POS, lemma, and whitespace data.
        Formatting runs are folded onto whole tokens before returning.
        Raises TokenizationCancelled if cancel() was called during processing.
        """
        if self._cancel_event.is_set():
            raise TokenizationCancelled()

        doc = doc_cache.get_doc(text)
        return self.tokens_from_doc(doc, format_runs)

    def tokens_from_doc(
        self,
        doc: Doc | Span,
        format_runs: Sequence[FormatRun] = (),
    ) -> list[Token]:
        """Build Token models from an already-parsed spaCy Doc or sentence Span.

        Lets a caller that has already parsed a whole paragraph reuse that one
        parse for each sentence (its span) instead of re-parsing each sentence
        in isolation. POS, lemma, and whitespace come straight from the tokens.
        Raises TokenizationCancelled if cancel() was called during processing.
        """
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
        if format_runs:
            apply_format_runs(tokens, format_runs)
        return tokens
