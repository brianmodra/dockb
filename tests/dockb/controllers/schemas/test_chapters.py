"""Tests for chapter request schemas."""

import pytest
from pydantic import ValidationError

from dockb.controllers.schemas.chapters import ChapterRelations, CreateChapterRequest, UpdateChapterRequest
from dockb.controllers.schemas.nodes import ChapterAttrs


def test_chapter_relations_minimal():
    r = ChapterRelations(document_id="d-1")
    assert r.document_id == "d-1"
    assert r.after_chapter_id is None


def test_chapter_relations_with_after():
    r = ChapterRelations(document_id="d-1", after_chapter_id="ch-0")
    assert r.after_chapter_id == "ch-0"


def test_create_chapter_request():
    req = CreateChapterRequest(
        attrs=ChapterAttrs(id="ch-1", title="Chapter 1"),
        relations=ChapterRelations(document_id="d-1"),
    )
    assert req.attrs.id == "ch-1"
    assert req.relations.document_id == "d-1"


def test_create_chapter_request_with_after():
    req = CreateChapterRequest(
        attrs=ChapterAttrs(id="ch-2", title="Chapter 2"),
        relations=ChapterRelations(document_id="d-1", after_chapter_id="ch-1"),
    )
    assert req.relations.after_chapter_id == "ch-1"


def test_update_chapter_request():
    req = UpdateChapterRequest(attrs=ChapterAttrs(id="ch-1", title="Updated"))
    assert req.attrs.title == "Updated"


def test_create_chapter_requires_relations():
    with pytest.raises(ValidationError):
        CreateChapterRequest(attrs=ChapterAttrs(id="ch-1", title="Ch"))


def test_create_chapter_requires_attrs():
    with pytest.raises(ValidationError):
        CreateChapterRequest(relations=ChapterRelations(document_id="d-1"))
