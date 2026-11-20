"""Sentence model for tokenization and text reconstruction."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from pydantic import Field, PrivateAttr

from dockb.models.formatting import FormatRun
from dockb.models.token import Token
from dockb.models.utils.dockb_collection import DockbCollection, DockbModelBase, InsertionMode

from .base import DataState, DockbModel


def sentence_from_record(record: Mapping[str, Any]) -> Sentence:
    """Build a Sentence from a graph record carrying dialogue properties."""
    start = record.get("sentence_dialogue_start_token")
    end = record.get("sentence_dialogue_end_token")
    return Sentence(
        id=record["sentence_id"],
        state=DataState.SYNC,
        is_dialogue=bool(record.get("sentence_is_dialogue", False)),
        dialogue_start_token=-1 if start is None else start,
        dialogue_end_token=-1 if end is None else end,
        dialogue_checked_at=record.get("sentence_dialogue_checked_at") or "",
        dialogue_spans=parse_dialogue_spans(record.get("sentence_dialogue_spans") or []),
    )


def flatten_dialogue_spans(spans: Sequence[tuple[int, int]]) -> list[int]:
    """Flatten inclusive token ranges into the Neo4j property list."""
    return [value for start, end in spans for value in (start, end)]


def parse_dialogue_spans(values: Sequence[int]) -> list[tuple[int, int]]:
    """Parse a Neo4j property list back into inclusive token ranges."""
    return [(values[index], values[index + 1]) for index in range(0, len(values) - 1, 2)]


class Sentence(DockbModel):
    """
    A sentence is a list of Tokens (word, punctuation, whitespace, extended).
    Text is reconstructed by concatenating tokens in order.
    Tokenization converts text into Token objects.
    """

    tokens: DockbCollection[Token] = Field(default_factory=DockbCollection)
    is_dialogue: bool = False
    dialogue_start_token: int = -1
    dialogue_end_token: int = -1
    dialogue_checked_at: str = ""
    dialogue_spans: list[tuple[int, int]] = Field(default_factory=list)
    _format_runs: list[FormatRun] = PrivateAttr(default_factory=list)

    @property
    def format_runs(self) -> list[FormatRun]:
        """Transient formatting runs, consumed when tokens are built."""
        return self._format_runs

    @format_runs.setter
    def format_runs(self, value: list[FormatRun]) -> None:
        self._format_runs = value

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
