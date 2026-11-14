"""Tests for converting wire nodes into in-memory models."""

from dockb.controllers.desugar import desugar_sentence
from dockb.controllers.schemas.nodes import SentenceAttrs, SentenceNode, TextNode
from dockb.models.formatting import FormatRun, Style, Weight


def _sentence(*content: TextNode) -> SentenceNode:
    return SentenceNode(attrs=SentenceAttrs(id="s-1"), content=list(content))


def test_desugar_sentence_sets_text_and_no_runs_for_plain_text():
    sent = desugar_sentence(_sentence(TextNode(text="Hello world.")))

    assert sent.text == "Hello world."
    assert not sent.format_runs


def test_desugar_sentence_converts_a_mark_to_a_character_range_run():
    sent = desugar_sentence(
        _sentence(
            TextNode(text="Hello "),
            TextNode(text="world.", marks=[{"type": "format", "attrs": {"style": "italic"}}]),
        )
    )

    assert sent.text == "Hello world."
    assert sent.format_runs == [FormatRun(6, 12, style=Style.ITALIC)]


def test_desugar_sentence_keeps_adjacent_runs_in_order():
    sent = desugar_sentence(
        _sentence(
            TextNode(text="a", marks=[{"type": "format", "attrs": {"style": "italic"}}]),
            TextNode(text="b", marks=[{"type": "format", "attrs": {"weight": "bold"}}]),
        )
    )

    assert sent.format_runs == [
        FormatRun(0, 1, style=Style.ITALIC),
        FormatRun(1, 2, weight=Weight.BOLD),
    ]


def test_desugar_sentence_ignores_a_fully_unset_mark():
    sent = desugar_sentence(_sentence(TextNode(text="Hello", marks=[{"type": "format", "attrs": {}}])))

    assert not sent.format_runs


def test_desugar_sentence_keeps_an_explicit_normal():
    sent = desugar_sentence(_sentence(TextNode(text="Hello", marks=[{"type": "format", "attrs": {"weight": "normal"}}])))

    assert sent.format_runs == [FormatRun(0, 5, weight=Weight.NORMAL)]
