"""Tests for the shared chapter-to-markdown serializer."""

from __future__ import annotations

import re

from dockb.infrastructure.markdown import writer
from dockb.models.chapter import Chapter
from dockb.models.paragraph import Paragraph
from dockb.models.sentence import Sentence
from dockb.models.token import Token


def _make_sentence(text: str) -> Sentence:
    token = Token()
    token.set_text(text)
    sentence = Sentence()
    sentence.tokens.append(token)
    return sentence


def _make_paragraph(*texts: str, p_id: str = "p1") -> Paragraph:
    paragraph = Paragraph(id=p_id)
    for text in texts:
        paragraph.sentences.append(_make_sentence(text))
    return paragraph


def _chapter(*paragraphs: Paragraph, c_id: str = "c1", title: str = "T") -> Chapter:
    chapter = Chapter(id=c_id, title=title)
    for paragraph in paragraphs:
        chapter.paragraphs.append(paragraph)
    return chapter


class TestSerializeBody:
    def test_single_paragraph(self, nlp):
        chapter = _chapter(_make_paragraph("First paragraph.", p_id="p1"))
        assert writer.serialize_body(chapter, nlp) == '<span data-par-id="p1">First paragraph.</span>'

    def test_paragraphs_separated_by_blank_line(self, nlp):
        chapter = _chapter(_make_paragraph("Para one.", p_id="p1"), _make_paragraph("Para two.", p_id="p2"))
        assert writer.serialize_body(chapter, nlp) == (
            '<span data-par-id="p1">Para one.</span>\n\n' '<span data-par-id="p2">Para two.</span>'
        )

    def test_sentence_per_line_inside_paragraph(self, nlp):
        chapter = _chapter(_make_paragraph("First sentence.", " Second sentence.", p_id="p1"))
        assert writer.serialize_body(chapter, nlp) == (
            '<span data-par-id="p1">First sentence.</span>\n' '<span data-par-id="p1"> Second sentence.</span>'
        )

    def test_spans_carry_paragraph_ids_and_no_sentence_id(self, nlp):
        chapter = _chapter(_make_paragraph("Alpha.", "Beta.", p_id="para-7"), _make_paragraph("Gamma.", p_id="para-8"))
        body = writer.serialize_body(chapter, nlp)
        assert body == (
            '<span data-par-id="para-7">Alpha.</span>\n'
            '<span data-par-id="para-7">Beta.</span>\n\n'
            '<span data-par-id="para-8">Gamma.</span>'
        )
        assert "data-sen-id" not in body

    def test_html_escapes_sentence_text(self, nlp):
        chapter = _chapter(_make_paragraph('A <span> tag & "quotes".', p_id="p1"))
        assert writer.serialize_body(chapter, nlp) == ('<span data-par-id="p1">' "A &lt;span&gt; tag &amp; &quot;quotes&quot;.</span>")

    def test_hard_break_preserved(self, nlp):
        chapter = _chapter(_make_paragraph("Line one\\\nline two. Next.", p_id="p1"))
        assert writer.serialize_body(chapter, nlp) == '<span data-par-id="p1">Line one\\\nline two. Next.</span>'

    def test_soft_newline_preserved(self, nlp):
        chapter = _chapter(_make_paragraph("First\nline. Second.", p_id="p1"))
        assert writer.serialize_body(chapter, nlp) == '<span data-par-id="p1">First\nline. Second.</span>'

    def test_empty_chapter_has_empty_body(self, nlp):
        assert writer.serialize_body(_chapter(), nlp) == ""

    def test_dirty_chapter_splits_raw_text_with_nlp(self, nlp):
        chapter = Chapter(id="c1", title="T")
        chapter.set_text("Dr. Smith arrived. He sat down.")
        body = writer.serialize_body(chapter, nlp)
        spans = re.findall(r'<span data-par-id="([^"]*)">([^<]*)</span>', body, flags=re.DOTALL)
        assert len(spans) == 2
        assert [text for _, text in spans] == ["Dr. Smith arrived. ", "He sat down."]
        assert spans[0][0] == spans[1][0]

    def test_sentence_less_paragraph_splits_with_nlp(self, nlp):
        paragraph = Paragraph(id="p1")
        paragraph.set_text("Foo bar.")
        body = writer.serialize_body(_chapter(paragraph), nlp)
        assert re.fullmatch(r'<span data-par-id="[^"]*">Foo bar.</span>', body)

    def test_is_idempotent(self, nlp):
        chapter = _chapter(_make_paragraph("First sentence.", " Second sentence.", p_id="p1"))
        assert writer.serialize_body(chapter, nlp) == writer.serialize_body(chapter, nlp)


class TestRenderChapterMarkdown:
    def test_renders_front_matter_and_body(self, nlp):
        chapter = _chapter(_make_paragraph("Hi.", p_id="p1"))
        assert writer.render_chapter_markdown(chapter, nlp) == ("---\nid: c1\ntitle: T\n---\n\n" '<span data-par-id="p1">Hi.</span>\n')

    def test_renders_front_matter_only_for_empty_chapter(self, nlp):
        assert writer.render_chapter_markdown(_chapter(), nlp) == "---\nid: c1\ntitle: T\n---\n"

    def test_attrs_drive_front_matter_verbatim(self, nlp):
        chapter = _chapter(_make_paragraph("Hi.", p_id="p1"))
        rendered = writer.render_chapter_markdown(chapter, nlp, attrs={"id": "c9", "title": "Other", "author": "Brian"})
        assert rendered == ("---\nid: c9\ntitle: Other\nauthor: Brian\n---\n\n" '<span data-par-id="p1">Hi.</span>\n')

    def test_write_chapter_markdown_writes_rendered_content(self, nlp, tmp_path):
        target = tmp_path / "chapter.md"
        chapter = _chapter(_make_paragraph("Hi.", p_id="p1"))
        writer.write_chapter_markdown(chapter, target, nlp)
        assert target.read_text() == writer.render_chapter_markdown(chapter, nlp)
