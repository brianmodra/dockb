"""Tests for model-to-wire-format serializers."""

from dockb.controllers.serializers import (
    serialize_chapter,
    serialize_chapter_summary,
    serialize_document,
    serialize_paragraph,
    serialize_sentence,
)
from dockb.models.chapter import Chapter
from dockb.models.document import Document
from dockb.models.paragraph import Paragraph
from dockb.models.sentence import Sentence


def _make_sentence(sid: str = "s-1", text: str = "Hello world.") -> Sentence:
    s = Sentence(id=sid)
    s.set_text(text)
    s.dirty = False
    return s


def _make_paragraph(pid: str = "p-1", sentences: list[Sentence] | None = None) -> Paragraph:
    p = Paragraph(id=pid)
    if sentences:
        for sent in sentences:
            p.append_child(sent)
    return p


def _make_chapter(cid: str = "ch-1", title: str = "Chapter 1", paragraphs: list[Paragraph] | None = None) -> Chapter:
    ch = Chapter(id=cid, title=title)
    if paragraphs:
        for para in paragraphs:
            ch.append_child(para)
    return ch


def _make_document(did: str = "d-1", title: str = "Book", author: str = "Author", chapters: list[Chapter] | None = None) -> Document:
    doc = Document(id=did, title=title, author=author)
    if chapters:
        for ch in chapters:
            doc.append_child(ch)
    return doc


# ---------------------------------------------------------------------------
# serialize_sentence
# ---------------------------------------------------------------------------


def test_serialize_sentence_basic():
    s = _make_sentence("s-1", "Hello world.")
    node = serialize_sentence(s)
    d = node.model_dump()
    assert d == {
        "type": "sentence",
        "attrs": {"id": "s-1"},
        "content": [{"type": "text", "text": "Hello world."}],
    }


def test_serialize_sentence_empty():
    s = Sentence(id="s-empty")
    node = serialize_sentence(s)
    assert node.content == []
    assert node.attrs.id == "s-empty"


def test_serialize_sentence_uses_get_text():
    s = _make_sentence("s-1", "First sentence.")
    s.dirty = False
    node = serialize_sentence(s)
    assert node.content[0].text == "First sentence."


def test_serialize_sentence_dirty_uses_raw_text():
    s = Sentence(id="s-dirty")
    s.text = "Unsaved edit"
    s.dirty = True
    node = serialize_sentence(s)
    assert node.content[0].text == "Unsaved edit"


# ---------------------------------------------------------------------------
# serialize_paragraph
# ---------------------------------------------------------------------------


def test_serialize_paragraph_empty():
    p = _make_paragraph("p-1")
    node = serialize_paragraph(p)
    d = node.model_dump()
    assert d == {
        "type": "paragraph",
        "attrs": {"id": "p-1"},
        "content": [],
    }


def test_serialize_paragraph_with_sentences():
    s1 = _make_sentence("s-1", "First.")
    s2 = _make_sentence("s-2", "Second.")
    p = _make_paragraph("p-1", [s1, s2])
    node = serialize_paragraph(p)
    assert len(node.content) == 2
    assert node.content[0].attrs.id == "s-1"
    assert node.content[0].content[0].text == "First."
    assert node.content[1].attrs.id == "s-2"
    assert node.content[1].content[0].text == "Second."


# ---------------------------------------------------------------------------
# serialize_chapter
# ---------------------------------------------------------------------------


def test_serialize_chapter_empty():
    ch = _make_chapter("ch-1", "Intro")
    node = serialize_chapter(ch)
    d = node.model_dump()
    assert d == {
        "type": "chapter",
        "attrs": {"id": "ch-1", "title": "Intro"},
        "content": [],
    }


def test_serialize_chapter_full_tree():
    s = _make_sentence("s-1", "Hello.")
    p = _make_paragraph("p-1", [s])
    ch = _make_chapter("ch-1", "Chapter 1", [p])
    node = serialize_chapter(ch)
    d = node.model_dump()
    assert d["type"] == "chapter"
    assert d["attrs"]["id"] == "ch-1"
    assert d["attrs"]["title"] == "Chapter 1"
    assert len(d["content"]) == 1
    assert d["content"][0]["type"] == "paragraph"
    assert d["content"][0]["attrs"]["id"] == "p-1"
    assert d["content"][0]["content"][0]["type"] == "sentence"
    assert d["content"][0]["content"][0]["content"][0]["text"] == "Hello."


def test_serialize_chapter_multiple_paragraphs():
    s1 = _make_sentence("s-1", "One.")
    s2 = _make_sentence("s-2", "Two.")
    p1 = _make_paragraph("p-1", [s1])
    p2 = _make_paragraph("p-2", [s2])
    ch = _make_chapter("ch-1", "Ch", [p1, p2])
    node = serialize_chapter(ch)
    assert len(node.content) == 2
    assert node.content[0].attrs.id == "p-1"
    assert node.content[1].attrs.id == "p-2"


# ---------------------------------------------------------------------------
# serialize_chapter_summary
# ---------------------------------------------------------------------------


def test_serialize_chapter_summary():
    ch = _make_chapter("ch-1", "Intro")
    summary = serialize_chapter_summary(ch)
    d = summary.model_dump()
    assert d == {"id": "ch-1", "title": "Intro"}


# ---------------------------------------------------------------------------
# serialize_document
# ---------------------------------------------------------------------------


def test_serialize_document_empty():
    doc = _make_document("d-1", "Book", "Author")
    d = serialize_document(doc)
    assert d == {
        "attrs": {"id": "d-1", "title": "Book", "author": "Author"},
        "chapter_summaries": [],
    }


def test_serialize_document_with_chapters():
    ch1 = _make_chapter("ch-1", "Chapter 1")
    ch2 = _make_chapter("ch-2", "Chapter 2")
    doc = _make_document("d-1", "Book", "Author", [ch1, ch2])
    d = serialize_document(doc)
    assert d["attrs"]["id"] == "d-1"
    assert len(d["chapter_summaries"]) == 2
    assert d["chapter_summaries"][0] == {"id": "ch-1", "title": "Chapter 1"}
    assert d["chapter_summaries"][1] == {"id": "ch-2", "title": "Chapter 2"}


def test_serialize_document_no_child_content():
    s = _make_sentence("s-1", "Hello.")
    p = _make_paragraph("p-1", [s])
    ch = _make_chapter("ch-1", "Ch", [p])
    doc = _make_document("d-1", "Book", "Author", [ch])
    d = serialize_document(doc)
    # chapter_summaries should only have attrs, not nested content
    assert "content" not in d["chapter_summaries"][0]
    assert d["chapter_summaries"][0] == {"id": "ch-1", "title": "Ch"}
