"""Tests for document request / response schemas."""

import pytest
from pydantic import ValidationError

from dockb.controllers.schemas.documents import (
    CreateDocumentRequest,
    DocumentAttrs,
    DocumentResponse,
    DocumentSummary,
    UpdateDocumentRequest,
)
from dockb.controllers.schemas.nodes import ChapterSummary


def test_document_attrs_full():
    a = DocumentAttrs(id="d-1", title="Faith", author="Paul")
    assert a.id == "d-1"
    assert a.title == "Faith"


def test_document_attrs_id_optional():
    a = DocumentAttrs(title="Hope", author="Peter")
    assert a.id is None


def test_document_attrs_allows_extra_fields():
    a = DocumentAttrs(title="x", author="y", premise="A story about...")
    assert a.premise == "A story about..."


def test_create_document_request():
    req = CreateDocumentRequest(
        attrs=DocumentAttrs(id="d-1", title="Faith", author="Paul"),
    )
    assert req.attrs.id == "d-1"


def test_update_document_request():
    req = UpdateDocumentRequest(attrs=DocumentAttrs(title="Love", author="John"))
    assert req.attrs.id is None
    assert req.attrs.title == "Love"


def test_update_document_request_with_id():
    req = UpdateDocumentRequest(attrs=DocumentAttrs(id="d-1", title="Love", author="John"))
    assert req.attrs.id == "d-1"


def test_document_response():
    resp = DocumentResponse(
        attrs=DocumentAttrs(id="d-1", title="Book", author="Writer"),
        chapter_summaries=[ChapterSummary(id="ch-1", title="Ch 1")],
    )
    d = resp.model_dump()
    assert d["attrs"]["id"] == "d-1"
    assert len(d["chapter_summaries"]) == 1
    assert d["chapter_summaries"][0]["title"] == "Ch 1"


def test_document_response_empty_chapters():
    resp = DocumentResponse(
        attrs=DocumentAttrs(id="d-1", title="Book", author="Writer"),
        chapter_summaries=[],
    )
    assert resp.chapter_summaries == []


def test_document_summary():
    s = DocumentSummary(id="d-1", title="Faith", author="Paul")
    d = s.model_dump()
    assert d == {"id": "d-1", "title": "Faith", "author": "Paul"}


def test_create_document_requires_attrs():
    with pytest.raises(ValidationError):
        CreateDocumentRequest()


def test_update_document_requires_attrs():
    with pytest.raises(ValidationError):
        UpdateDocumentRequest()
