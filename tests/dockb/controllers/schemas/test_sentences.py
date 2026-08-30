"""Tests for sentence request schemas."""

import pytest
from pydantic import ValidationError

from dockb.controllers.schemas.nodes import SentenceAttrs, TextNode
from dockb.controllers.schemas.sentences import (
    CreateSentenceRequest,
    SentenceRelations,
    UpdateSentenceRelations,
    UpdateSentenceRequest,
)


def _text(text: str = "Hello.") -> TextNode:
    return TextNode(text=text)


def test_sentence_relations_minimal():
    r = SentenceRelations(paragraph_id="p-1")
    assert r.paragraph_id == "p-1"
    assert r.after_sentence_id is None


def test_sentence_relations_with_after():
    r = SentenceRelations(paragraph_id="p-1", after_sentence_id="s-0")
    assert r.after_sentence_id == "s-0"


def test_update_sentence_relations_all_optional():
    r = UpdateSentenceRelations()
    assert r.paragraph_id is None
    assert r.after_sentence_id is None


def test_update_sentence_relations_with_reparent():
    r = UpdateSentenceRelations(paragraph_id="p-2", after_sentence_id="s-5")
    assert r.paragraph_id == "p-2"


def test_create_sentence_request():
    req = CreateSentenceRequest(
        attrs=SentenceAttrs(id="s-1"),
        content=[_text("Hello world.")],
        relations=SentenceRelations(paragraph_id="p-1"),
    )
    assert req.attrs.id == "s-1"
    assert len(req.content) == 1
    assert req.content[0].text == "Hello world."


def test_create_sentence_request_multiple_text_nodes():
    req = CreateSentenceRequest(
        attrs=SentenceAttrs(id="s-1"),
        content=[_text("Hello "), _text("world.")],
        relations=SentenceRelations(paragraph_id="p-1"),
    )
    assert len(req.content) == 2


def test_update_sentence_request_content_only():
    req = UpdateSentenceRequest(
        attrs=SentenceAttrs(id="s-1"),
        content=[_text("Updated.")],
    )
    assert req.relations is None


def test_update_sentence_request_with_relations():
    req = UpdateSentenceRequest(
        attrs=SentenceAttrs(id="s-1"),
        content=[_text("Moved.")],
        relations=UpdateSentenceRelations(paragraph_id="p-2"),
    )
    assert req.relations.paragraph_id == "p-2"


def test_create_sentence_allows_empty_content():
    req = CreateSentenceRequest(
        attrs=SentenceAttrs(id="s-1"),
        content=[],
        relations=SentenceRelations(paragraph_id="p-1"),
    )
    assert req.content == []


def test_update_sentence_allows_empty_content():
    req = UpdateSentenceRequest(
        attrs=SentenceAttrs(id="s-1"),
        content=[],
    )
    assert req.content == []


def test_create_sentence_requires_relations():
    with pytest.raises(ValidationError):
        CreateSentenceRequest(
            attrs=SentenceAttrs(id="s-1"),
            content=[_text("x")],
        )
