"""Span scanning for the canonical markdown.

Paragraph identity spans can contain nested inline-formatting spans. These
helpers find the outermost spans and strip the tags when only text is wanted.
"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass

from dockb.models.formatting import Family, Style, Weight

_TAG_RE = re.compile(r"<span\b([^>]*)>|</span>", re.DOTALL | re.IGNORECASE)


@dataclass(frozen=True)
class Span:
    """One outermost ``<span>`` and its raw inner markup."""

    attrs: str
    inner: str
    start: int
    end: int


def find_spans(text: str) -> list[Span]:
    """Return the outermost spans in *text*, leaving nested spans in ``inner``."""
    spans: list[Span] = []
    stack: list[tuple[int, str, int]] = []
    for tag in _TAG_RE.finditer(text):
        if tag.group(0).startswith("</"):
            if not stack:
                continue
            start, attrs, open_end = stack.pop()
            if not stack:
                spans.append(Span(attrs, text[open_end : tag.start()], start, tag.end()))
        else:
            stack.append((tag.start(), tag.group(1), tag.end()))
    return spans


def strip_span_tags(text: str) -> str:
    """Remove span open and close tags from raw inner markup."""
    return _TAG_RE.sub("", text)


def plain_text(inner: str) -> str:
    """Return the visible text of raw span inner markup."""
    return html.unescape(strip_span_tags(inner))


def render_style(style: Style, weight: Weight, family: Family, size: str) -> str:
    """Render the set formatting attributes as a CSS declaration list."""
    declarations: list[str] = []
    for name, value in (("font-style", style), ("font-weight", weight), ("font-family", family)):
        if value.value:
            declarations.append(f"{name}: {value.value}")
    if size:
        declarations.append(f"font-size: {size}")
    return "; ".join(declarations)
