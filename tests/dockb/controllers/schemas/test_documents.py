"""Tests for document request / response schemas."""

import pytest
from pydantic import ValidationError

from dockb.controllers.schemas.documents import (
    CreateDocumentRequest,
    DocumentAttrs,
    DocumentResponse,
    DocumentSummary,
    NarrativePerspective,
    NarrativePerspectivesResponse,
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


def test_document_attrs_defaults_narrative_perspective_to_empty():
    a = DocumentAttrs(title="Faith", author="Paul")
    assert a.narrative_perspective == ""


def test_document_attrs_accepts_a_known_narrative_perspective():
    a = DocumentAttrs(title="Faith", author="Paul", narrative_perspective="third_person_limited")
    assert a.narrative_perspective == "third_person_limited"


def test_document_attrs_rejects_an_unknown_narrative_perspective():
    with pytest.raises(ValidationError, match="(?i)narrative perspective"):
        DocumentAttrs(title="Faith", author="Paul", narrative_perspective="unknown")


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
    assert d == {"id": "d-1", "title": "Faith", "author": "Paul", "narrative_perspective": ""}


def test_document_summary_carries_the_narrative_perspective():
    s = DocumentSummary(id="d-1", title="Faith", author="Paul", narrative_perspective="epistolary")
    assert s.model_dump()["narrative_perspective"] == "epistolary"


def test_narrative_perspective_schema():
    p = NarrativePerspective(code="first_person", label="First Person")
    assert p.model_dump() == {"code": "first_person", "label": "First Person"}


def test_narrative_perspectives_response():
    resp = NarrativePerspectivesResponse(perspectives=[NarrativePerspective(code="first_person", label="First Person")])
    assert resp.model_dump() == {"perspectives": [{"code": "first_person", "label": "First Person"}]}


def test_create_document_requires_attrs():
    with pytest.raises(ValidationError):
        CreateDocumentRequest()


def test_update_document_requires_attrs():
    with pytest.raises(ValidationError):
        UpdateDocumentRequest()


def test_document_attrs_rejects_blank_title():
    with pytest.raises(ValidationError):
        DocumentAttrs(title="", author="Paul")


def test_document_attrs_rejects_whitespace_title():
    with pytest.raises(ValidationError):
        DocumentAttrs(title="   ", author="Paul")
