"""Inline formatting attributes carried by tokens.

Formatting is stored on tokens, not as separate marks. ``FormatRun`` is the
transient carrier used between parsing text and tokenizing it; once tokens
exist the runs are folded onto them and cleared.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum
from typing import Literal, TypeAlias

LayoutKind: TypeAlias = Literal["normal", "quoted"]
LayoutVariant: TypeAlias = Literal["", "reading", "writing"]

LAYOUT_KINDS: tuple[LayoutKind, ...] = ("normal", "quoted")
LAYOUT_VARIANTS: tuple[LayoutVariant, ...] = ("", "reading", "writing")


class Style(Enum):
    """Character style; ``_`` means unset (inherited)."""

    ITALIC = "italic"
    UNDERLINE = "underline"
    NORMAL = "normal"
    _ = ""


class Weight(Enum):
    """Font weight; ``_`` means unset (inherited)."""

    BOLD = "bold"
    NORMAL = "normal"
    _ = ""


class Family(Enum):
    """Font family; ``_`` means unset (inherited)."""

    MONOSPACE = "monospace"
    NORMAL = "normal"
    _ = ""


_SIZE_RE = re.compile(r"^\d+(\.\d+)?em$")


def validate_layout(kind: LayoutKind, variant: LayoutVariant) -> None:
    """Reject a layout whose variant does not match its kind."""
    if kind == "quoted":
        if variant not in ("reading", "writing"):
            raise ValueError("a quoted paragraph needs a 'reading' or 'writing' variant")
    elif variant:
        raise ValueError("a normal paragraph must not have a layout variant")


def validate_size(value: str) -> str:
    """Validate a font size expressed in ``em``; ``""`` means unset.

    A set size must be a positive multiple of ``em``, e.g. ``0.5em`` or ``2em``.
    """
    if value == "":
        return value
    if not _SIZE_RE.fullmatch(value):
        raise ValueError(f"'{value}' is not a size in em")
    if float(value[: -len("em")]) <= 0:
        raise ValueError(f"'{value}' must be a positive size")
    return value


@dataclass(frozen=True)
class FormatRun:
    """One inline formatting run over a character range of a text."""

    start: int
    end: int
    style: Style = Style._
    weight: Weight = Weight._
    family: Family = Family._
    size: str = ""

    def __post_init__(self) -> None:
        """Reject an inverted, negative, or invalid run."""
        if self.start < 0 or self.end < self.start:
            raise ValueError("a format run needs a non-negative, ordered range")
        validate_size(self.size)


def slice_runs(runs: Sequence[FormatRun], start: int, end: int) -> list[FormatRun]:
    """Clip *runs* to ``[start, end)`` and rebase their offsets to *start*."""
    clipped: list[FormatRun] = []
    for run in runs:
        overlap_start = max(run.start, start)
        overlap_end = min(run.end, end)
        if overlap_start >= overlap_end:
            continue
        clipped.append(
            FormatRun(
                overlap_start - start,
                overlap_end - start,
                style=run.style,
                weight=run.weight,
                family=run.family,
                size=run.size,
            )
        )
    return clipped
