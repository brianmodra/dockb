"""Tests for ProseMirror node schemas."""

import pytest
from pydantic import ValidationError

from dockb.controllers.schemas.nodes import (
    ChapterAttrs,
    ChapterNode,
    ChapterSummary,
    ParagraphAttrs,
    ParagraphNode,
    SentenceAttrs,
    SentenceNode,
    TextNode,
)

# ---------------------------------------------------------------------------
# TextNode
# ---------------------------------------------------------------------------


def test_text_node_serializes():
    node = TextNode(text="Hello world.")
    d = node.model_dump()
    assert d == {"type": "text", "text": "Hello world."}


def test_text_node_type_is_literal():
    node = TextNode(text="x")
    assert node.type == "text"


# ---------------------------------------------------------------------------
# SentenceNode
# ---------------------------------------------------------------------------


def test_sentence_node_round_trip():
    node = SentenceNode(
        attrs=SentenceAttrs(id="s-1"),
        content=[TextNode(text="Hello.")],
    )
    d = node.model_dump()
    assert d["type"] == "sentence"
    assert d["attrs"]["id"] == "s-1"
    assert d["content"][0]["text"] == "Hello."


def test_sentence_node_empty_content():
    node = SentenceNode(attrs=SentenceAttrs(id="s-2"), content=[])
    assert node.content == []


# ---------------------------------------------------------------------------
# ParagraphNode
# ---------------------------------------------------------------------------


def test_paragraph_node_round_trip():
    node = ParagraphNode(
        attrs=ParagraphAttrs(id="p-1"),
        content=[
            SentenceNode(
                attrs=SentenceAttrs(id="s-1"),
                content=[TextNode(text="First.")],
            ),
            SentenceNode(
                attrs=SentenceAttrs(id="s-2"),
                content=[TextNode(text="Second.")],
            ),
        ],
    )
    d = node.model_dump()
    assert d["type"] == "paragraph"
    assert len(d["content"]) == 2
    assert d["content"][0]["attrs"]["id"] == "s-1"
    assert d["content"][1]["content"][0]["text"] == "Second."


# ---------------------------------------------------------------------------
# ChapterNode
# ---------------------------------------------------------------------------


def test_chapter_node_full_tree():
    node = ChapterNode(
        attrs=ChapterAttrs(id="ch-1", title="Chapter 1"),
        content=[
            ParagraphNode(
                attrs=ParagraphAttrs(id="p-1"),
                content=[
                    SentenceNode(
                        attrs=SentenceAttrs(id="s-1"),
                        content=[TextNode(text="Hello world.")],
                    )
                ],
            )
        ],
    )
    d = node.model_dump()
    assert d["type"] == "chapter"
    assert d["attrs"]["title"] == "Chapter 1"
    assert d["content"][0]["type"] == "paragraph"
    assert d["content"][0]["content"][0]["type"] == "sentence"
    assert d["content"][0]["content"][0]["content"][0]["text"] == "Hello world."


# ---------------------------------------------------------------------------
# Extra attrs (extensibility)
# ---------------------------------------------------------------------------


def test_sentence_attrs_allows_extra_fields():
    node = SentenceNode(
        attrs=SentenceAttrs(id="s-1", custom_field="value"),
        content=[TextNode(text="x")],
    )
    assert node.attrs.custom_field == "value"


def test_paragraph_attrs_allows_extra_fields():
    node = ParagraphNode(
        attrs=ParagraphAttrs(id="p-1", future_field=42),
        content=[],
    )
    assert node.attrs.future_field == 42


def test_chapter_attrs_allows_extra_fields():
    node = ChapterNode(
        attrs=ChapterAttrs(id="ch-1", title="Ch", color="red"),
        content=[],
    )
    assert node.attrs.color == "red"


# ---------------------------------------------------------------------------
# Missing required fields
# ---------------------------------------------------------------------------


def test_sentence_attrs_id_is_optional():
    attrs = SentenceAttrs()
    assert attrs.id is None


def test_paragraph_attrs_id_is_optional():
    attrs = ParagraphAttrs()
    assert attrs.id is None


def test_chapter_attrs_requires_id_and_title():
    with pytest.raises(ValidationError):
        ChapterAttrs(id="ch-1")


# ---------------------------------------------------------------------------
# ChapterSummary
# ---------------------------------------------------------------------------


def test_chapter_summary():
    s = ChapterSummary(id="ch-1", title="Intro")
    d = s.model_dump()
    assert d == {"id": "ch-1", "title": "Intro"}
