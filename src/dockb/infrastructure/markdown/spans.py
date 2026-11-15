"""Span scanning for the canonical markdown.

Paragraph identity spans can contain nested inline-formatting spans. These
helpers find the outermost spans and strip the tags when only text is wanted.
"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass

from dockb.models.formatting import Family, FormatRun, Style, Weight, validate_size

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


_STYLE_ATTR_RE = re.compile(r'\bstyle="([^"]*)"')


def formatting_from_markup(markup: str) -> tuple[str, list[FormatRun]]:
    """Return the visible text and formatting runs of raw span inner markup."""
    parts: list[str] = []
    runs: list[FormatRun] = []
    cursor = 0
    length = 0
    for span in find_spans(markup):
        prefix = html.unescape(markup[cursor : span.start])
        parts.append(prefix)
        length += len(prefix)
        child_text, child_runs = formatting_from_markup(span.inner)
        style, weight, family, size = parse_style_attributes(span.attrs)
        if child_text and any((style.value, weight.value, family.value, size)):
            runs.append(FormatRun(length, length + len(child_text), style, weight, family, size))
        runs.extend(shift_runs(child_runs, length))
        parts.append(child_text)
        length += len(child_text)
        cursor = span.end
    tail = html.unescape(markup[cursor:])
    parts.append(tail)
    return "".join(parts), merge_runs(runs)


def parse_style_attributes(attrs: str) -> tuple[Style, Weight, Family, str]:
    """Read font declarations from a span's ``style`` attribute, ignoring unknowns."""
    style = Style._
    weight = Weight._
    family = Family._
    size = ""
    match = _STYLE_ATTR_RE.search(attrs)
    if not match:
        return style, weight, family, size
    for declaration in match.group(1).split(";"):
        name, separator, value = declaration.partition(":")
        if not separator:
            continue
        name = name.strip().lower()
        value = value.strip()
        try:
            if name == "font-style":
                style = Style(value)
            elif name == "font-weight":
                weight = Weight(value)
            elif name == "font-family":
                family = Family(value)
            elif name == "font-size":
                size = validate_size(value)
        except ValueError:
            continue
    return style, weight, family, size


def merge_runs(runs: list[FormatRun]) -> list[FormatRun]:
    """Combine touching runs that carry the same formatting."""
    merged: list[FormatRun] = []
    for run in runs:
        if run.start >= run.end:
            continue
        previous = merged[-1] if merged else None
        if (
            previous
            and previous.end == run.start
            and (
                previous.style,
                previous.weight,
                previous.family,
                previous.size,
            )
            == (run.style, run.weight, run.family, run.size)
        ):
            merged[-1] = FormatRun(previous.start, run.end, previous.style, previous.weight, previous.family, previous.size)
        else:
            merged.append(run)
    return merged


def shift_runs(runs: list[FormatRun], offset: int) -> list[FormatRun]:
    """Return *runs* moved forward by *offset* characters."""
    return [FormatRun(run.start + offset, run.end + offset, run.style, run.weight, run.family, run.size) for run in runs]


def render_style(style: Style, weight: Weight, family: Family, size: str) -> str:
    """Render the set formatting attributes as a CSS declaration list."""
    declarations: list[str] = []
    for name, value in (("font-style", style), ("font-weight", weight), ("font-family", family)):
        if value.value:
            declarations.append(f"{name}: {value.value}")
    if size:
        declarations.append(f"font-size: {size}")
    return "; ".join(declarations)
