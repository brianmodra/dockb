"""Tests for detect_changes — paragraph-level change detection."""

from __future__ import annotations

from collections.abc import Callable

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


def _span(par_id: str, *lines: str) -> str:
    """A canonical paragraph identity span holding one sentence line per *line*."""
    return f'<span data-par-id="{par_id}">\n' + "\n".join(lines) + "\n</span>"


def _front_matter(chapter_id: str = "c-1") -> str:
    return f'---\nid: "{chapter_id}"\ntitle: "T"\n---\n\n'


def _get_old(old: Chapter) -> Callable[[str], Chapter | None]:
    """A get_chapter stub returning *old* for its own id, None otherwise."""

    def get(chapter_id: str) -> Chapter | None:
        return old if chapter_id == old.id else None

    return get


def _no_create(*_args, **_kwargs) -> Chapter:
    raise AssertionError("create_chapter should not be called")


def _no_get(*_args, **_kwargs) -> Chapter | None:
    raise AssertionError("get_chapter should not be called")


def test_changed_paragraph_carries_new_text():
    old = _chapter([("par-1", ["First sentence. ", "Second sentence."])])
    body = _span("par-1", "First sentence changed.", "Second sentence.")

    diff = detect_changes(_front_matter() + body, _get_old(old), _no_create)

    assert diff.changed == [ChangedParagraph(par_id="par-1", text="First sentence changed.\nSecond sentence.")]
    assert not diff.new
    assert not diff.deleted


def test_unchanged_paragraph_is_omitted():
    old = _chapter([("par-1", ["First.\n", "Second."])])
    body = _span("par-1", "First.", "Second.")

    diff = detect_changes(_front_matter() + body, _get_old(old), _no_create)

    assert not diff
    assert not diff.changed
    assert not diff.new
    assert not diff.deleted


def test_span_free_block_is_new_without_split():
    old = _chapter([("par-1", ["Known."])])
    body = "Plain paragraph. Second sentence."

    diff = detect_changes(_front_matter() + body, _get_old(old), _no_create)

    assert diff.new == [NewParagraph(text="Plain paragraph. Second sentence.", at_start=True)]
    assert not diff.changed
    assert diff.deleted == ["par-1"]


def test_span_bearing_block_with_unknown_id_is_new():
    old = _chapter([("par-1", ["Known."])])
    body = _span("ghost", "Unknown paragraph.")

    diff = detect_changes(_front_matter() + body, _get_old(old), _no_create)

    assert diff.new == [NewParagraph(text="Unknown paragraph.", at_start=True)]
    assert diff.deleted == ["par-1"]
    assert "ghost" not in diff.deleted


def test_paragraph_absent_from_new_file_is_deleted():
    old = _chapter(
        [
            ("par-1", ["First. "]),
            ("par-2", ["Second."]),
            ("par-3", ["Third. "]),
        ]
    )
    body = _span("par-2", "Second.")

    diff = detect_changes(_front_matter() + body, _get_old(old), _no_create)

    assert diff.deleted == ["par-1", "par-3"]
    assert not diff.changed
    assert not diff.new


def test_empty_body_deletes_everything():
    old = _chapter([("par-1", ["First. "]), ("par-2", ["Second. "])])

    diff = detect_changes(_front_matter(), _get_old(old), _no_create)

    assert diff.deleted == ["par-1", "par-2"]
    assert not diff.changed
    assert not diff.new


def test_span_inner_content_is_html_unescaped():
    old = _chapter([("par-1", ['A <span> tag & "quotes".'])])
    body = _span("par-1", "A &lt;span&gt; tag &amp; &quot;quotes&quot;.")

    diff = detect_changes(_front_matter() + body, _get_old(old), _no_create)

    assert not diff


def test_mid_sentence_newline_inside_span_is_preserved():
    old = _chapter([("par-1", ["First\nline. Still first."])])
    body = _span("par-1", "First\nline. Still first.")

    diff = detect_changes(_front_matter() + body, _get_old(old), _no_create)

    assert not diff


def test_dirty_old_paragraph_compared_as_opaque_string():
    old_chapter = Chapter(id="c-1")
    paragraph = Paragraph(id="par-1")
    paragraph.set_text("Hand typed. ")
    old_chapter.paragraphs.append(paragraph)
    body = '<span data-par-id="par-1">\nHand typed. \n</span>'

    diff = detect_changes(_front_matter() + body, _get_old(old_chapter), _no_create)

    assert not diff


def test_trailing_whitespace_change_is_reported():
    old = _chapter([("par-1", ["Hello world."])])
    body = '<span data-par-id="par-1">\nHello world. \n</span>'

    diff = detect_changes(_front_matter() + body, _get_old(old), _no_create)

    assert diff.changed == [ChangedParagraph(par_id="par-1", text="Hello world. ")]


def test_merge_is_delete_plus_changed():
    old = _chapter([("par-1", ["A. "]), ("par-2", ["B. "])])
    body = _span("par-1", "A. B.")

    diff = detect_changes(_front_matter() + body, _get_old(old), _no_create)

    assert diff.changed == [ChangedParagraph(par_id="par-1", text="A. B.")]
    assert diff.deleted == ["par-2"]
    assert not diff.new


def test_loose_text_in_span_bearing_block_is_kept_in_place():
    old = _chapter([("par-1", ["One.", "Four."])])
    body = '<span data-par-id="par-1">\nOne.\n</span>\n' "Loose two. Loose three.\n" '<span data-par-id="par-1">\nFour.\n</span>'

    diff = detect_changes(_front_matter() + body, _get_old(old), _no_create)

    assert diff.changed == [ChangedParagraph(par_id="par-1", text="One.\nLoose two. Loose three.\nFour.")]
    assert not diff.deleted


def test_appended_line_after_closing_span_belongs_to_paragraph():
    old = _chapter([("par-1", ["Known."])])
    body = _span("par-1", "Known.") + "\nAppended sentence."

    diff = detect_changes(_front_matter() + body, _get_old(old), _no_create)

    assert diff.changed == [ChangedParagraph(par_id="par-1", text="Known.\nAppended sentence.")]


def test_edit_inside_paragraph_span_is_detected():
    old = _chapter([("par-1", ["First.\n", "Second."])])
    body = _span("par-1", "First.", "Second — tweaked.")

    diff = detect_changes(_front_matter() + body, _get_old(old), _no_create)

    assert diff.changed == [ChangedParagraph(par_id="par-1", text="First.\nSecond — tweaked.")]


def test_mixed_changed_and_new_and_deleted():
    old = _chapter(
        [
            ("par-1", ["Old one. "]),
            ("par-2", ["Two."]),
            ("par-3", ["Three. "]),
        ]
    )
    body = _span("par-1", "New one.") + "\n\n" + _span("par-4", "Fresh.") + "\n\n" + _span("par-2", "Two.") + "\n\n" + "Hand typed block."

    diff = detect_changes(_front_matter() + body, _get_old(old), _no_create)

    assert diff.changed == [ChangedParagraph(par_id="par-1", text="New one.")]
    assert diff.deleted == ["par-3"]
    assert diff.new[-1] == NewParagraph(text="Hand typed block.", after_id="par-2")
    assert NewParagraph(text="Fresh.", after_id="par-1") in diff.new
    assert not any(changed.par_id == "par-2" for changed in diff.changed)


def test_diff_carries_the_resolved_chapter_id():
    old = _chapter([("par-1", ["First. "])])
    body = _span("par-1", "First.")

    diff = detect_changes(_front_matter() + body, _get_old(old), _no_create)

    assert diff.chapter_id == "c-1"


def test_no_front_matter_is_a_new_chapter():
    created_ids: list[str | None] = []
    created_titles: list[str] = []
    created = Chapter(id="c-fresh")

    def create_chapter(chapter_id: str | None, title: str) -> Chapter:
        created_ids.append(chapter_id)
        created_titles.append(title)
        return created

    diff = detect_changes("Brand new paragraph. Second sentence.", _no_get, create_chapter, title_fallback="Fallback")

    assert created_ids == [None]
    assert created_titles == ["Fallback"]
    assert diff.chapter_id == "c-fresh"
    assert diff.title == "Fallback"
    assert diff.front_id is None
    assert diff.created is True
    assert diff.new == [NewParagraph(text="Brand new paragraph. Second sentence.")]
    assert not diff.deleted


def test_front_matter_without_id_is_a_new_chapter():
    created = Chapter(id="c-fresh")
    content = '---\ntitle: "T"\n---\n\nLonesome paragraph.'

    diff = detect_changes(content, _get_old(_chapter([])), lambda _chapter_id, title: created)

    assert diff.chapter_id == "c-fresh"
    assert diff.title == "T"
    assert diff.front_id is None
    assert diff.created is True
    assert diff.new == [NewParagraph(text="Lonesome paragraph.")]


def test_front_matter_id_is_used_to_lookup_the_old_chapter():
    old = _chapter([("par-1", ["First."])])
    lookups: list[str] = []

    def get_chapter(chapter_id: str) -> Chapter | None:
        lookups.append(chapter_id)
        return old

    diff = detect_changes(_front_matter() + _span("par-1", "First."), get_chapter, _no_create)

    assert lookups == ["c-1"]
    assert diff.chapter_id == "c-1"
    assert diff.title == "T"
    assert diff.front_id == "c-1"
    assert diff.created is False
    assert not diff


def test_front_matter_id_with_no_kg_chapter_creates_with_that_id():
    created_ids: list[str | None] = []
    created_titles: list[str] = []

    def create_chapter(chapter_id: str | None, title: str) -> Chapter:
        created_ids.append(chapter_id)
        created_titles.append(title)
        return Chapter(id=chapter_id or "generated")

    diff = detect_changes(
        _front_matter("c-9") + _span("par-1", "One."),
        lambda _chapter_id: None,
        create_chapter,
    )

    assert created_ids == ["c-9"]
    assert created_titles == ["T"]
    assert diff.chapter_id == "c-9"
    assert diff.title == "T"
    assert diff.front_id == "c-9"
    assert diff.created is True
    assert diff.new == [NewParagraph(text="One.")]


def test_consecutive_new_paragraphs_share_the_anchor():
    old = _chapter([("par-1", ["Known."])])
    body = _span("par-1", "Known.") + "\n\n" + "Brand new A.\n\n" + "Brand new B."

    diff = detect_changes(_front_matter() + body, _get_old(old), _no_create)

    assert diff.new == [
        NewParagraph(text="Brand new A.", after_id="par-1"),
        NewParagraph(text="Brand new B.", after_id="par-1"),
    ]
    assert not diff.changed
    assert not diff.deleted


def test_leading_new_paragraphs_are_at_start():
    old = _chapter([("par-1", ["Known."])])
    body = "Brand new A.\n\nBrand new B.\n\n" + _span("par-1", "Known.")

    diff = detect_changes(_front_matter() + body, _get_old(old), _no_create)

    assert diff.new == [
        NewParagraph(text="Brand new A.", at_start=True),
        NewParagraph(text="Brand new B.", at_start=True),
    ]
    assert not diff.changed
    assert not diff.deleted


def test_new_paragraph_after_changed_uses_its_id():
    old = _chapter([("par-1", ["Old one. "])])
    body = _span("par-1", "New one.") + "\n\nBrand new."

    diff = detect_changes(_front_matter() + body, _get_old(old), _no_create)

    assert diff.changed == [ChangedParagraph(par_id="par-1", text="New one.")]
    assert diff.new == [NewParagraph(text="Brand new.", after_id="par-1")]


def test_new_paragraph_after_unchanged_uses_its_id():
    old = _chapter([("par-1", ["Known."])])
    body = "Brand new.\n\n" + _span("par-1", "Known.") + "\n\nAlso new."

    diff = detect_changes(_front_matter() + body, _get_old(old), _no_create)

    assert diff.new == [
        NewParagraph(text="Brand new.", at_start=True),
        NewParagraph(text="Also new.", after_id="par-1"),
    ]


def test_front_matter_title_wins_over_fallback():
    created = Chapter(id="c-fresh")
    content = '---\ntitle: "FM Title"\n---\n\nLonesome paragraph.'
    res: list[str] = []

    def create_chapter(_chapter_id: str | None, title: str) -> Chapter:
        res.append(title)
        return created

    diff = detect_changes(content, _get_old(_chapter([])), create_chapter, title_fallback="Fallback")

    assert res == ["FM Title"]
    assert diff.title == "FM Title"


def test_front_matter_without_title_uses_fallback():
    created = Chapter(id="c-fresh")
    content = '---\nid: "c-9"\n---\n\nLonesome paragraph.'
    res: list[str] = []

    def create_chapter(_chapter_id: str | None, title: str) -> Chapter:
        res.append(title)
        return created

    diff = detect_changes(content, lambda _chapter_id: None, create_chapter, title_fallback="Fallback")

    assert res == ["Fallback"]
    assert diff.title == "Fallback"


def test_missing_closing_front_matter_raises():
    old = _chapter([("par-1", ["First. "])])
    content = '---\nid: "c-1"\n' + _span("par-1", "First.")

    with pytest.raises(ChapterMismatchError):
        detect_changes(content, _get_old(old), _no_create)
