"""Tests for dialogue span detection and quote normalization."""

from __future__ import annotations

import pytest

from dockb.services.dialogue import (
    CLOSING_QUOTE,
    DOUBLE_QUOTE_CHARS,
    OPENING_QUOTE,
    DialogueResult,
    DialogueSpan,
    QuoteCorrection,
    find_dialogue,
    token_quote_fixes,
    token_spans,
)


def _spans(result: DialogueResult) -> list[tuple[int, int, int, int, int, bool]]:
    return [(span.paragraph, span.sentence, span.start, span.end, span.group, span.continues) for span in result.spans]


def _corrections(result: DialogueResult) -> list[tuple[int, int, int, str]]:
    return [(fix.paragraph, fix.sentence, fix.offset, fix.replacement) for fix in result.corrections]


def _quote_offsets(*texts: str) -> list[int]:
    return [index for text in texts for index, char in enumerate(text) if char in DOUBLE_QUOTE_CHARS]


def test_a_paragraph_with_no_quotes_has_no_dialogue() -> None:
    result = find_dialogue([["He shrugged. Nothing more was said."]])

    assert not result.spans
    assert not result.corrections


def test_two_dialogue_spans_in_one_sentence() -> None:
    text = 'He said, "It is a very nice day!" Mary replied, "Yes, I agree."'
    first, second, third, fourth = _quote_offsets(text)

    result = find_dialogue([[text]])

    assert _spans(result) == [
        (0, 0, first + 1, second, 1, False),
        (0, 0, third + 1, fourth, 2, False),
    ]
    assert _corrections(result) == [
        (0, 0, first, OPENING_QUOTE),
        (0, 0, second, CLOSING_QUOTE),
        (0, 0, third, OPENING_QUOTE),
        (0, 0, fourth, CLOSING_QUOTE),
    ]


@pytest.mark.parametrize("mark", sorted(DOUBLE_QUOTE_CHARS))
def test_every_supported_quote_mark_is_normalized_by_position(mark: str) -> None:
    text = f"X{mark}hello{mark}Y"
    opening, closing = _quote_offsets(text)

    result = find_dialogue([[text]])

    assert _corrections(result) == [
        (0, 0, opening, OPENING_QUOTE),
        (0, 0, closing, CLOSING_QUOTE),
    ]
    assert _spans(result) == [(0, 0, opening + 1, closing, 1, False)]


def test_left_quote_used_to_close_is_rewritten_as_a_right_quote() -> None:
    text = '"Hello “'
    opening, closing = _quote_offsets(text)

    result = find_dialogue([[text]])

    assert _corrections(result) == [
        (0, 0, opening, OPENING_QUOTE),
        (0, 0, closing, CLOSING_QUOTE),
    ]


def test_dialogue_spanning_sentences_is_reported_per_sentence() -> None:
    first_sentence = '"It is a nice day! '
    second_sentence = 'It is warm."'
    third_sentence = ' Then "Hello," she said.'
    opening = _quote_offsets(first_sentence)[0]
    closing = _quote_offsets(second_sentence)[0]
    next_opening, next_closing = _quote_offsets(third_sentence)

    result = find_dialogue([[first_sentence, second_sentence, third_sentence]])

    assert _spans(result) == [
        (0, 0, opening + 1, len(first_sentence), 1, False),
        (0, 1, 0, closing, 1, False),
        (0, 2, next_opening + 1, next_closing, 2, False),
    ]


def test_dialogue_spanning_paragraphs_keeps_one_group() -> None:
    first = 'He said, "It was a fine day'
    second = '"And then it rained," she said.'
    first_quote = _quote_offsets(first)[0]
    leading, closing = _quote_offsets(second)

    result = find_dialogue([[first], [second]])

    assert _spans(result) == [
        (0, 0, first_quote + 1, len(first), 1, True),
        (1, 0, leading + 1, closing, 1, False),
    ]
    assert _corrections(result) == [
        (0, 0, first_quote, OPENING_QUOTE),
        (1, 0, leading, OPENING_QUOTE),
        (1, 0, closing, CLOSING_QUOTE),
    ]


def test_leading_whitespace_before_a_quote_still_continues_dialogue() -> None:
    first = '"It was a fine day'
    second = '   "And then it rained," she said.'
    first_quote = _quote_offsets(first)[0]
    leading, closing = _quote_offsets(second)

    result = find_dialogue([[first], [second]])

    assert _spans(result) == [
        (0, 0, first_quote + 1, len(first), 1, True),
        (1, 0, leading + 1, closing, 1, False),
    ]


def test_multi_paragraph_dialogue_continues_through_more_than_two_paragraphs() -> None:
    first = '"One'
    middle = '"Two'
    last = '"Three," she said.'
    first_quote = _quote_offsets(first)[0]
    middle_quote = _quote_offsets(middle)[0]
    leading, closing = _quote_offsets(last)

    result = find_dialogue([[first], [middle], [last]])

    assert _spans(result) == [
        (0, 0, first_quote + 1, len(first), 1, True),
        (1, 0, middle_quote + 1, len(middle), 1, True),
        (2, 0, leading + 1, closing, 1, False),
    ]


def test_unbounded_dialogue_produces_no_span_and_no_fix() -> None:
    first = 'He said, "It was a fine day'
    second = "And then it rained, she said."

    result = find_dialogue([[first], [second]])

    assert not result.spans
    assert not result.corrections


def test_unbounded_at_end_of_chapter_produces_no_span() -> None:
    result = find_dialogue([['He said, "It was a fine day']])

    assert not result.spans
    assert not result.corrections


def test_an_unbounded_span_discards_its_earlier_continuation_fragments() -> None:
    first = '"One'
    middle = '"Two'
    last = "Three, she said."

    result = find_dialogue([[first], [middle], [last]])

    assert not result.spans
    assert not result.corrections


def test_a_valid_dialogue_after_an_error_is_still_found() -> None:
    broken = 'He said, "oops'
    valid = 'Then "Hello," she said.'
    valid_open, valid_close = _quote_offsets(valid)

    result = find_dialogue([[broken], [valid]])

    assert _spans(result) == [(1, 0, valid_open + 1, valid_close, 1, False)]
    assert _corrections(result) == [
        (1, 0, valid_open, OPENING_QUOTE),
        (1, 0, valid_close, CLOSING_QUOTE),
    ]


def test_token_spans_maps_character_range_to_inclusive_token_indices() -> None:
    tokens = [("He", " "), ("said,", " "), ("“", " "), ("It", " "), ("is", " "), ("nice", " "), ("day!", ""), ("”", "")]
    span = DialogueSpan(paragraph=0, sentence=0, start=10, end=26, group=0, continues=False)

    assert token_spans(tokens, [span]) == [(3, 6)]


def test_token_spans_returns_one_range_per_span() -> None:
    tokens = [('"', " "), ("Hi", " "), ('"', " "), ("she", " "), ("said", " "), ('"', " "), ("Bye", " "), ('"', "")]
    first = DialogueSpan(paragraph=0, sentence=0, start=2, end=5, group=0, continues=False)
    second = DialogueSpan(paragraph=0, sentence=0, start=18, end=22, group=1, continues=False)

    assert token_spans(tokens, [first, second]) == [(1, 1), (6, 6)]


def test_token_quote_fixes_rewrites_mark_tokens() -> None:
    tokens = [('"', " "), ("Hello", " "), ('"', "")]

    fixes = token_quote_fixes(
        tokens,
        [
            QuoteCorrection(paragraph=0, sentence=0, offset=0, replacement=OPENING_QUOTE),
            QuoteCorrection(paragraph=0, sentence=0, offset=8, replacement=CLOSING_QUOTE),
        ],
    )

    assert fixes == {0: (OPENING_QUOTE, " "), 2: (CLOSING_QUOTE, "")}


def test_token_quote_fixes_rewrites_quote_inside_token_text() -> None:
    tokens = [('"Hello', " "), ('world"', "")]

    fixes = token_quote_fixes(
        tokens,
        [
            QuoteCorrection(paragraph=0, sentence=0, offset=0, replacement=OPENING_QUOTE),
            QuoteCorrection(paragraph=0, sentence=0, offset=12, replacement=CLOSING_QUOTE),
        ],
    )

    assert fixes == {0: ("“Hello", " "), 1: ("world”", "")}


def test_token_quote_fixes_ignores_offsets_in_whitespace() -> None:
    tokens = [("Hello", " "), ("world", "")]

    assert not token_quote_fixes(tokens, [QuoteCorrection(paragraph=0, sentence=0, offset=5, replacement=OPENING_QUOTE)])
