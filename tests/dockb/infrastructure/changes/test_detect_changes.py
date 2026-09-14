"""Tests for detect_changes — paragraph-level change detection."""

from __future__ import annotations

import pytest

from dockb.exceptions import ChapterMismatchError
from dockb.infrastructure.changes.detect_changes import (
    ChangedParagraph,
    NewParagraph,
    detect_changes,
)
from dockb.models.chapter import Chapter
from dockb.models.paragraph import Paragraph
from dockb.models.sentence import Sentence


def _chapter(paragraphs: list[tuple[str, list[str]]]) -> Chapter:
    """Build a hydrated chapter from ``(par_id, sentence_texts)`` tuples."""
    chapter = Chapter(id="c-1")
    for par_id, sentence_texts in paragraphs:
        paragraph = Paragraph(id=par_id)
        for sentence_text in sentence_texts:
            sentence = Sentence()
            sentence.set_text(sentence_text)
            paragraph.sentences.append(sentence)
        chapter.paragraphs.append(paragraph)
    return chapter


def _front_matter(chapter_id: str = "c-1") -> str:
    return f'---\nid: "{chapter_id}"\ntitle: "T"\n---\n\n'


def test_changed_paragraph_carries_new_sentence_texts():
    old = _chapter([("par-1", ["First sentence. ", "Second sentence."])])
    body = '<span data-par-id="par-1">First sentence changed. </span>\n<span data-par-id="par-1">Second sentence.</span>'

    diff = detect_changes(old, _front_matter() + body, None)

    assert diff.changed == [ChangedParagraph(par_id="par-1", sentence_texts=["First sentence changed. ", "Second sentence."])]
    assert not diff.new
    assert not diff.deleted


def test_unchanged_paragraph_is_omitted():
    old = _chapter([("par-1", ["First. ", "Second."])])
    body = '<span data-par-id="par-1">First. </span>\n<span data-par-id="par-1">Second.</span>'

    diff = detect_changes(old, _front_matter() + body, None)

    assert not diff
    assert not diff.changed
    assert not diff.new
    assert not diff.deleted


def test_span_free_block_is_new_and_nlp_split(nlp):
    old = _chapter([("par-1", ["Known."])])
    body = "Plain paragraph. Second sentence."

    diff = detect_changes(old, _front_matter() + body, nlp)

    assert diff.new == [NewParagraph(sentence_texts=["Plain paragraph. ", "Second sentence."])]
    assert not diff.changed
    assert diff.deleted == ["par-1"]


def test_span_free_block_survives_any_nlp_call(nlp):
    old = _chapter([])

    diff = detect_changes(old, _front_matter() + "Lonesome paragraph.", nlp)

    assert diff.new == [NewParagraph(sentence_texts=["Lonesome paragraph."])]


def test_span_bearing_block_with_unknown_id_is_new():
    old = _chapter([("par-1", ["Known."])])
    body = '<span data-par-id="ghost">Unknown paragraph.</span>'

    diff = detect_changes(old, _front_matter() + body, None)

    assert diff.new == [NewParagraph(sentence_texts=["Unknown paragraph."])]
    assert diff.deleted == ["par-1"]
    assert "ghost" not in diff.deleted


def test_paragraph_absent_from_new_file_is_deleted():
    old = _chapter(
        [
            ("par-1", ["First. "]),
            ("par-2", ["Second. "]),
            ("par-3", ["Third. "]),
        ]
    )
    body = '<span data-par-id="par-2">Second. </span>'

    diff = detect_changes(old, _front_matter() + body, None)

    assert diff.deleted == ["par-1", "par-3"]
    assert not diff.changed
    assert not diff.new


def test_empty_body_deletes_everything():
    old = _chapter([("par-1", ["First. "]), ("par-2", ["Second. "])])

    diff = detect_changes(old, _front_matter(), None)

    assert diff.deleted == ["par-1", "par-2"]
    assert not diff.changed
    assert not diff.new


def test_front_matter_id_mismatch_raises():
    old = _chapter([("par-1", ["First. "])])

    with pytest.raises(ChapterMismatchError):
        detect_changes(old, _front_matter("c-9") + '<span data-par-id="par-1">First. </span>', None)


def test_missing_front_matter_raises():
    old = _chapter([("par-1", ["First. "])])

    with pytest.raises(ChapterMismatchError):
        detect_changes(old, '<span data-par-id="par-1">First. </span>', None)


def test_front_matter_id_missing_raises():
    old = _chapter([("par-1", ["First. "])])
    content = '---\ntitle: "T"\n---\n\n<span data-par-id="par-1">First. </span>'

    with pytest.raises(ChapterMismatchError):
        detect_changes(old, content, None)


def test_span_inner_content_is_html_unescaped():
    old = _chapter([("par-1", ['A <span> tag & "quotes".'])])
    body = '<span data-par-id="par-1">A &lt;span&gt; tag &amp; &quot;quotes&quot;.</span>'

    diff = detect_changes(old, _front_matter() + body, None)

    assert not diff


def test_mid_sentence_newline_inside_span_is_preserved():
    old = _chapter([("par-1", ["First\nline. Still first."])])
    body = '<span data-par-id="par-1">First\nline. Still first.</span>'

    diff = detect_changes(old, _front_matter() + body, None)

    assert not diff


def test_dirty_old_paragraph_compared_as_opaque_string():
    old_chapter = Chapter(id="c-1")
    paragraph = Paragraph(id="par-1")
    paragraph.set_text("Hand typed. ")
    old_chapter.paragraphs.append(paragraph)
    body = '<span data-par-id="par-1">Hand typed. </span>'

    diff = detect_changes(old_chapter, _front_matter() + body, None)

    assert not diff


def test_trailing_whitespace_change_is_reported():
    old = _chapter([("par-1", ["Hello world."])])
    body = '<span data-par-id="par-1">Hello world. </span>'

    diff = detect_changes(old, _front_matter() + body, None)

    assert diff.changed == [ChangedParagraph(par_id="par-1", sentence_texts=["Hello world. "])]


def test_merge_is_delete_plus_changed():
    old = _chapter([("par-1", ["A. "]), ("par-2", ["B. "])])
    body = '<span data-par-id="par-1">A. B. </span>'

    diff = detect_changes(old, _front_matter() + body, None)

    assert diff.changed == [ChangedParagraph(par_id="par-1", sentence_texts=["A. B. "])]
    assert diff.deleted == ["par-2"]
    assert not diff.new


def test_loose_text_in_span_bearing_block_is_nlp_split_in_place(nlp):
    old = _chapter([("par-1", ["One. ", "Four. "])])
    body = '<span data-par-id="par-1">One. </span>\nLoose two. Loose three.\n<span data-par-id="par-1">Four. </span>'

    diff = detect_changes(old, _front_matter() + body, nlp)

    assert diff.changed == [ChangedParagraph(par_id="par-1", sentence_texts=["One. ", "\nLoose two. ", "Loose three.\n", "Four. "])]
    assert not diff.deleted


def test_mixed_changed_and_new_and_deleted(nlp):
    old = _chapter(
        [
            ("par-1", ["Old one. "]),
            ("par-2", ["Two. "]),
            ("par-3", ["Three. "]),
        ]
    )
    body = (
        '<span data-par-id="par-1">New one. </span>\n\n'
        '<span data-par-id="par-4">Fresh. </span>\n\n'
        '<span data-par-id="par-2">Two. </span>\n\n'
        "Hand typed block."
    )

    diff = detect_changes(old, "---\nid: c-1\ntitle: T\n---\n\n" + body, nlp)

    assert diff.changed == [ChangedParagraph(par_id="par-1", sentence_texts=["New one. "])]
    assert diff.deleted == ["par-3"]
    assert diff.new[-1] == NewParagraph(sentence_texts=["Hand typed block."])
    assert NewParagraph(sentence_texts=["Fresh. "]) in diff.new
    assert not any(changed.par_id == "par-2" for changed in diff.changed)
