"""Tests for paragraph request schemas."""

import pytest
from pydantic import ValidationError

from dockb.controllers.schemas.nodes import ParagraphAttrs, SentenceAttrs, SentenceNode, TextNode
from dockb.controllers.schemas.paragraphs import (
    CreateParagraphRequest,
    ParagraphRelations,
    UpdateParagraphRelations,
    UpdateParagraphRequest,
)


def _sentence(sid: str = "s-1", text: str = "Hello.") -> SentenceNode:
    return SentenceNode(attrs=SentenceAttrs(id=sid), content=[TextNode(text=text)])


def test_paragraph_relations_minimal():
    r = ParagraphRelations(chapter_id="ch-1")
    assert r.chapter_id == "ch-1"
    assert r.after_paragraph_id is None


def test_paragraph_relations_with_after():
    r = ParagraphRelations(chapter_id="ch-1", after_paragraph_id="p-0")
    assert r.after_paragraph_id == "p-0"


def test_update_paragraph_relations_all_optional():
    r = UpdateParagraphRelations()
    assert r.chapter_id is None
    assert r.after_paragraph_id is None


def test_update_paragraph_relations_with_reparent():
    r = UpdateParagraphRelations(chapter_id="ch-2", after_paragraph_id="p-5")
    assert r.chapter_id == "ch-2"


def test_create_paragraph_request():
    req = CreateParagraphRequest(
        attrs=ParagraphAttrs(id="p-1"),
        content=[_sentence("s-1", "Hello world.")],
        relations=ParagraphRelations(chapter_id="ch-1"),
    )
    assert req.attrs.id == "p-1"
    assert len(req.content) == 1
    assert req.content[0].attrs.id == "s-1"


def test_create_paragraph_request_multiple_sentences():
    req = CreateParagraphRequest(
        attrs=ParagraphAttrs(id="p-1"),
        content=[_sentence("s-1", "First."), _sentence("s-2", "Second.")],
        relations=ParagraphRelations(chapter_id="ch-1"),
    )
    assert len(req.content) == 2


def test_update_paragraph_request_content_only():
    req = UpdateParagraphRequest(
        attrs=ParagraphAttrs(id="p-1"),
        content=[_sentence("s-1", "Updated.")],
    )
    assert req.relations is None


def test_update_paragraph_request_with_relations():
    req = UpdateParagraphRequest(
        attrs=ParagraphAttrs(id="p-1"),
        content=[_sentence("s-1", "Moved.")],
        relations=UpdateParagraphRelations(chapter_id="ch-2"),
    )
    assert req.relations.chapter_id == "ch-2"


def test_create_paragraph_requires_content():
    with pytest.raises(ValidationError):
        CreateParagraphRequest(
            attrs=ParagraphAttrs(id="p-1"),
            content=[],
            relations=ParagraphRelations(chapter_id="ch-1"),
        )


def test_update_paragraph_requires_content():
    with pytest.raises(ValidationError):
        UpdateParagraphRequest(
            attrs=ParagraphAttrs(id="p-1"),
            content=[],
        )


def test_create_paragraph_requires_relations():
    with pytest.raises(ValidationError):
        CreateParagraphRequest(
            attrs=ParagraphAttrs(id="p-1"),
            content=[_sentence()],
        )
