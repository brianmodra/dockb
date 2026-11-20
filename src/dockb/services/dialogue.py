"""Dialogue detection and quotation-mark normalization.

Dialogue spans are read from a chapter's paragraphs as runs of text between
double-quote characters. Any of the characters in ``DOUBLE_QUOTE_CHARS`` may
open or close a span; position, not glyph, decides the role. Opening marks are
normalized to U+201C and closing marks to U+201D.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, replace

DOUBLE_QUOTE_CHARS = frozenset(
    {
        '"',
        "“",
        "”",
        "„",
        "‟",
        "«",
        "»",
        "〝",
        "〞",
        "〟",
        "＂",
    }
)

OPENING_QUOTE = "“"
CLOSING_QUOTE = "”"


@dataclass(frozen=True)
class QuoteCorrection:
    """One quotation mark to rewrite, addressed inside a sentence."""

    paragraph: int
    sentence: int
    offset: int
    replacement: str


@dataclass(frozen=True)
class DialogueSpan:
    """The dialogue text inside one sentence, as character offsets."""

    paragraph: int
    sentence: int
    start: int
    end: int
    group: int
    continues: bool


@dataclass(frozen=True)
class DialogueResult:
    """The dialogue found in a chapter, and the quote fixes it implies."""

    spans: list[DialogueSpan]
    corrections: list[QuoteCorrection]


def find_dialogue(paragraphs: Sequence[Sequence[str]]) -> DialogueResult:
    """Find dialogue spans across *paragraphs* and the quote fixes they need.

    Each inner sequence holds one paragraph's sentence texts. Quote marks are
    paired by position: the first opens, the next closes. A span left open at
    a paragraph boundary continues when the following paragraph starts with a
    quote mark; otherwise that opening mark is an error and no span is kept.
    """
    chunks = [_chunk(sentences) for sentences in paragraphs]
    quotes = [
        (paragraph, offset)
        for paragraph, (_, _, text) in enumerate(chunks)
        for offset, char in enumerate(text)
        if char in DOUBLE_QUOTE_CHARS
    ]

    spans: list[DialogueSpan] = []
    corrections: list[QuoteCorrection] = []
    group = 0
    cursor = 0
    while cursor < len(quotes):
        local_spans, local_corrections, next_cursor = _read_dialogue(chunks, quotes, cursor, group + 1)
        if next_cursor is not None:
            group += 1
            spans.extend(local_spans)
            corrections.extend(local_corrections)
            cursor = next_cursor
        else:
            cursor += 1
    return DialogueResult(spans=spans, corrections=corrections)


def _chunk(sentences: Sequence[str]) -> tuple[list[str], list[int], str]:
    """One paragraph's sentence texts, their start offsets, and joined text."""
    texts = list(sentences)
    offsets: list[int] = []
    position = 0
    for text in texts:
        offsets.append(position)
        position += len(text)
    return texts, offsets, "".join(texts)


def _read_dialogue(  # pylint: disable=too-many-locals
    chunks: list[tuple[list[str], list[int], str]],
    quotes: list[tuple[int, int]],
    cursor: int,
    group: int,
) -> tuple[list[DialogueSpan], list[QuoteCorrection], int | None]:
    """Walk one logical dialogue from its opening mark to its close or failure.

    A ``None`` cursor means the opening mark was unbounded: the caller drops
    every fragment and correction collected here.
    """
    spans: list[DialogueSpan] = []
    corrections: list[QuoteCorrection] = []
    paragraph, offset = quotes[cursor]
    opening_cursor = cursor
    while True:
        texts, offsets, text = chunks[paragraph]
        close_cursor = next((i for i in range(opening_cursor + 1, len(quotes)) if quotes[i][0] == paragraph), None)
        if close_cursor is not None:
            close_offset = quotes[close_cursor][1]
            spans.extend(_fragments(paragraph, texts, offsets, offset + 1, close_offset, group, continues=False))
            corrections.append(_correction(paragraph, offsets, offset, OPENING_QUOTE))
            corrections.append(_correction(paragraph, offsets, close_offset, CLOSING_QUOTE))
            return spans, corrections, close_cursor + 1

        continuation = _continuation(chunks, paragraph, quotes, opening_cursor)
        if continuation is None:
            return spans, corrections, None
        leading_offset, leading_cursor = continuation
        spans.extend(_fragments(paragraph, texts, offsets, offset + 1, len(text), group, continues=True))
        corrections.append(_correction(paragraph, offsets, offset, OPENING_QUOTE))
        paragraph, offset, opening_cursor = paragraph + 1, leading_offset, leading_cursor


def _continuation(
    chunks: list[tuple[list[str], list[int], str]],
    paragraph: int,
    quotes: list[tuple[int, int]],
    opening_cursor: int,
) -> tuple[int, int] | None:
    """The leading quote of the next paragraph, when it continues the dialogue."""
    next_paragraph = paragraph + 1
    if next_paragraph >= len(chunks):
        return None
    text = chunks[next_paragraph][2]
    leading = next((index for index, char in enumerate(text) if char in DOUBLE_QUOTE_CHARS), None)
    if leading is None or text[:leading].strip():
        return None
    return leading, quotes.index((next_paragraph, leading), opening_cursor + 1)


def _correction(paragraph: int, offsets: list[int], offset: int, replacement: str) -> QuoteCorrection:
    sentence = max(index for index, start in enumerate(offsets) if start <= offset)
    return QuoteCorrection(paragraph=paragraph, sentence=sentence, offset=offset, replacement=replacement)


def _fragments(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    paragraph: int,
    texts: list[str],
    offsets: list[int],
    start: int,
    end: int,
    group: int,
    *,
    continues: bool,
) -> list[DialogueSpan]:
    """Split one paragraph-level character range into per-sentence spans."""
    fragments = [
        DialogueSpan(
            paragraph=paragraph,
            sentence=sentence,
            start=max(start, offsets[sentence]) - offsets[sentence],
            end=min(end, offsets[sentence] + len(text)) - offsets[sentence],
            group=group,
            continues=False,
        )
        for sentence, text in enumerate(texts)
        if min(end, offsets[sentence] + len(text)) > max(start, offsets[sentence])
    ]
    if fragments and continues:
        fragments[-1] = replace(fragments[-1], continues=True)
    return fragments


def token_spans(tokens: Sequence[tuple[str, str]], spans: Sequence[DialogueSpan]) -> list[tuple[int, int]]:
    """Turn sentence-relative character ranges into inclusive token indices."""
    text_ranges: list[tuple[int, int]] = []
    position = 0
    for text, trailing_ws in tokens:
        text_ranges.append((position, position + len(text)))
        position += len(text) + len(trailing_ws)

    result: list[tuple[int, int]] = []
    for span in spans:
        overlapping = [index for index, (start, end) in enumerate(text_ranges) if span.start < end and span.end > start]
        if overlapping:
            result.append((overlapping[0], overlapping[-1]))
    return result


def token_quote_fixes(
    tokens: Sequence[tuple[str, str]],
    corrections: Sequence[QuoteCorrection],
) -> dict[int, tuple[str, str]]:
    """Turn quote corrections into corrected (text, trailing_ws) per token."""
    text_ranges: list[tuple[int, int]] = []
    position = 0
    for text, trailing_ws in tokens:
        text_ranges.append((position, position + len(text)))
        position += len(text) + len(trailing_ws)

    fixes: dict[int, tuple[str, str]] = {}
    for correction in corrections:
        for index, (start, end) in enumerate(text_ranges):
            if start <= correction.offset < end:
                text, trailing_ws = fixes.get(index, tokens[index])
                relative = correction.offset - start
                fixes[index] = (text[:relative] + correction.replacement + text[relative + 1 :], trailing_ws)
                break
    return fixes
