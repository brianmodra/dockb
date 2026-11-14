"""Inline formatting attributes carried by tokens.

Formatting is stored on tokens, not as separate marks. ``FormatRun`` is the
transient carrier used between parsing text and tokenizing it; once tokens
exist the runs are folded onto them and cleared.
"""

from __future__ import annotations

import re
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
