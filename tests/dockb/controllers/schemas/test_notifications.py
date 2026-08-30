"""Tests for notification payload schemas."""

from dockb.controllers.schemas.nodes import (
    ParagraphAttrs,
    ParagraphNode,
    SentenceAttrs,
    SentenceNode,
    TextNode,
)
from dockb.controllers.schemas.notifications import (
    NotificationsResponse,
    ParagraphSplitNotification,
    SentenceSplitNotification,
)


def _sentence(sid: str = "s-1", text: str = "Hello.") -> SentenceNode:
    return SentenceNode(attrs=SentenceAttrs(id=sid), content=[TextNode(text=text)])


def _paragraph(pid: str = "p-1", sentences: list[SentenceNode] | None = None) -> ParagraphNode:
    return ParagraphNode(attrs=ParagraphAttrs(id=pid), content=sentences or [_sentence()])


def test_sentence_split_notification():
    n = SentenceSplitNotification(
        paragraph_id="p-1",
        changed_sentences=[_sentence("s-1", "Part one."), _sentence("s-2", "Part two.")],
    )
    d = n.model_dump()
    assert d["type"] == "sentence_split"
    assert d["paragraph_id"] == "p-1"
    assert len(d["changed_sentences"]) == 2
    assert d["changed_sentences"][0]["attrs"]["id"] == "s-1"
    assert d["changed_sentences"][0]["content"][0]["text"] == "Part one."


def test_sentence_split_uses_prosemirror_format():
    n = SentenceSplitNotification(
        paragraph_id="p-1",
        changed_sentences=[_sentence()],
    )
    s = n.changed_sentences[0]
    assert s.type == "sentence"
    assert s.attrs.id == "s-1"
    assert s.content[0].type == "text"


def test_paragraph_split_notification():
    n = ParagraphSplitNotification(
        chapter_id="ch-1",
        changed_paragraphs=[_paragraph("p-1"), _paragraph("p-2")],
    )
    d = n.model_dump()
    assert d["type"] == "paragraph_split"
    assert d["chapter_id"] == "ch-1"
    assert len(d["changed_paragraphs"]) == 2
    assert d["changed_paragraphs"][0]["type"] == "paragraph"
    assert d["changed_paragraphs"][0]["content"][0]["type"] == "sentence"


def test_paragraph_split_includes_nested_sentence_splits():
    n = ParagraphSplitNotification(
        chapter_id="ch-1",
        changed_paragraphs=[
            _paragraph("p-1", [_sentence("s-1", "A."), _sentence("s-2", "B.")]),
        ],
    )
    assert len(n.changed_paragraphs[0].content) == 2


def test_notifications_response_empty():
    r = NotificationsResponse(notifications=[])
    d = r.model_dump()
    assert d == {"notifications": []}


def test_notifications_response_mixed_types():
    r = NotificationsResponse(
        notifications=[
            SentenceSplitNotification(paragraph_id="p-1", changed_sentences=[_sentence()]),
            ParagraphSplitNotification(chapter_id="ch-1", changed_paragraphs=[_paragraph()]),
        ]
    )
    assert len(r.notifications) == 2
    assert r.notifications[0].type == "sentence_split"
    assert r.notifications[1].type == "paragraph_split"
