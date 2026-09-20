"""Tests for SnapshotReader — markdown-to-chapter deserialization."""

from __future__ import annotations

import subprocess
import uuid

import pytest

from dockb.exceptions import SnapshotError
from dockb.infrastructure.history.snapshot_reader import SnapshotReader
from dockb.infrastructure.history.snapshot_writer import SnapshotWriter


@pytest.fixture()
def git_repo(tmp_path):
    """Create a temporary git repository."""
    subprocess.run(["git", "init"], cwd=str(tmp_path), check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=str(tmp_path), check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=str(tmp_path), check=True, capture_output=True)
    return tmp_path


@pytest.fixture()
def reader(git_repo, nlp):
    return SnapshotReader(base_dir=git_repo, nlp=nlp)


def _write_snapshot(git_repo, *, chapter_id: str, title: str, body: str) -> None:
    """Helper: write a raw snapshot file directly."""
    path = git_repo / f"chapter-{chapter_id}.md"
    path.write_text(f'---\nid: "{chapter_id}"\ntitle: "{title}"\n---\n\n{body}\n')
    subprocess.run(["git", "add", str(path)], cwd=str(git_repo), check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", f"snapshot: {chapter_id[:8]}"],
        cwd=str(git_repo),
        check=True,
        capture_output=True,
    )


def test_read_chapter_text(reader, git_repo):
    _write_snapshot(git_repo, chapter_id="c-aaa", title="T", body="Hello world.")
    chapter = reader.read_chapter("c-aaa")
    assert chapter.get_text() == "Hello world."


def test_read_front_matter_attrs(reader, git_repo):
    _write_snapshot(git_repo, chapter_id="c-bbb", title="My Title", body="Text.")
    chapter = reader.read_chapter("c-bbb")
    assert chapter.id == "c-bbb"
    assert chapter.title == "My Title"


def test_read_single_paragraph(reader, git_repo):
    _write_snapshot(git_repo, chapter_id="c-ccc", title="T", body="Single paragraph.")
    chapter = reader.read_chapter("c-ccc")
    assert len(chapter.paragraphs) == 1
    assert chapter.paragraphs[0].get_text() == "Single paragraph."


def test_read_multiple_paragraphs(reader, git_repo):
    _write_snapshot(git_repo, chapter_id="c-ddd", title="T", body="First paragraph.\n\nSecond paragraph.\n\nThird paragraph.")
    chapter = reader.read_chapter("c-ddd")
    assert len(chapter.paragraphs) == 3
    assert chapter.paragraphs[0].get_text() == "First paragraph."
    assert chapter.paragraphs[1].get_text() == "Second paragraph."
    assert chapter.paragraphs[2].get_text() == "Third paragraph."


def test_read_empty_body(reader, git_repo):
    _write_snapshot(git_repo, chapter_id="c-eee", title="Empty", body="")
    chapter = reader.read_chapter("c-eee")
    assert chapter.id == "c-eee"
    assert len(chapter.paragraphs) == 0


def test_read_paragraph_has_sentences(reader, git_repo):
    _write_snapshot(git_repo, chapter_id="c-fff", title="T", body="Dirty text.")
    chapter = reader.read_chapter("c-fff")
    assert len(chapter.paragraphs) == 1
    assert len(chapter.paragraphs[0].sentences) == 1
    assert chapter.paragraphs[0].sentences[0].text == "Dirty text."


def test_read_raw_content(reader, git_repo):
    _write_snapshot(git_repo, chapter_id="c-ggg", title="T", body="Raw content.")
    content = reader.read("c-ggg")
    assert 'id: "c-ggg"' in content
    assert "Raw content." in content


def test_read_missing_file_raises(reader):
    with pytest.raises(SnapshotError):
        reader.read_chapter("c-nonexistent")


def test_read_at_commit(reader, git_repo, nlp):  # pylint: disable=too-many-locals
    from dockb.models.chapter import Chapter
    from dockb.models.paragraph import Paragraph
    from dockb.models.sentence import Sentence
    from dockb.models.token import Token

    writer = SnapshotWriter(base_dir=git_repo, nlp=nlp)

    ch = Chapter(id="c-hhh", title="V1")
    token = Token()
    token.set_text("Version one.")
    sentence = Sentence()
    sentence.tokens.append(token)
    ch.paragraphs.append(Paragraph())
    ch.paragraphs[0].sentences.append(sentence)
    commit1 = writer.write(ch)

    ch.title = "V2"
    ch.paragraphs.clear()
    token2 = Token()
    token2.set_text("Version two.")
    sentence2 = Sentence()
    sentence2.tokens.append(token2)
    ch.paragraphs.append(Paragraph())
    ch.paragraphs[0].sentences.append(sentence2)
    commit2 = writer.write(ch)

    # Read at commit1 — should get V1
    chapter_v1 = reader.read_chapter("c-hhh", commit_id=commit1)
    assert chapter_v1.title == "V1"
    assert chapter_v1.get_text() == "Version one."

    # Read at commit2 — should get V2
    chapter_v2 = reader.read_chapter("c-hhh", commit_id=commit2)
    assert chapter_v2.title == "V2"
    assert chapter_v2.get_text() == "Version two."

    # Read current — should get V2
    chapter_current = reader.read_chapter("c-hhh")
    assert chapter_current.title == "V2"
    assert chapter_current.get_text() == "Version two."


def test_read_extras_in_front_matter(reader, git_repo):
    _write_snapshot(git_repo, chapter_id="c-iii", title="T", body="Body.")
    # Overwrite file to include extras
    path = git_repo / "chapter-c-iii.md"
    path.write_text('---\nid: "c-iii"\ntitle: "T"\npremise: "A premise"\norder: 1\n---\n\nBody.\n')
    subprocess.run(["git", "add", str(path)], cwd=str(git_repo), check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "add extras"],
        cwd=str(git_repo),
        check=True,
        capture_output=True,
    )
    chapter = reader.read_chapter("c-iii")
    assert chapter.title == "T"
    assert chapter.get_text() == "Body."
    # Extras are preserved in _snapshot_extras for forward compatibility
    extras = getattr(chapter, "_snapshot_extras", {})
    assert extras.get("premise") == "A premise"
    assert extras.get("order") == 1


def test_read_sentences_per_line(reader, git_repo):
    _write_snapshot(git_repo, chapter_id="c-jjj", title="T", body="First sentence.\n Second sentence.")
    chapter = reader.read_chapter("c-jjj")
    paragraph = chapter.paragraphs[0]
    assert len(paragraph.sentences) == 2
    assert paragraph.sentences[0].text == "First sentence.\n "
    assert paragraph.sentences[1].text == "Second sentence."
    assert chapter.get_text() == "First sentence.\n Second sentence."


def test_read_sentences_single_line(reader, git_repo):
    _write_snapshot(git_repo, chapter_id="c-kkk", title="T", body="First sentence. Second sentence.")
    chapter = reader.read_chapter("c-kkk")
    paragraph = chapter.paragraphs[0]
    assert len(paragraph.sentences) == 2
    assert paragraph.sentences[0].text == "First sentence. "
    assert paragraph.sentences[1].text == "Second sentence."
    assert chapter.get_text() == "First sentence. Second sentence."


def test_read_mid_sentence_newline(reader, git_repo):
    _write_snapshot(git_repo, chapter_id="c-lll", title="T", body="First\nline. Second.")
    chapter = reader.read_chapter("c-lll")
    paragraph = chapter.paragraphs[0]
    assert len(paragraph.sentences) == 2
    assert paragraph.sentences[0].text == "First\nline. "
    assert paragraph.sentences[1].text == "Second."
    assert chapter.get_text() == "First\nline. Second."


def test_read_hard_break_preserved(reader, git_repo):
    _write_snapshot(git_repo, chapter_id="c-mmm", title="T", body="Line one\\\nline two. Next.")
    chapter = reader.read_chapter("c-mmm")
    paragraph = chapter.paragraphs[0]
    assert len(paragraph.sentences) == 2
    assert paragraph.sentences[0].text == "Line one\\\nline two. "
    assert paragraph.sentences[1].text == "Next."
    assert chapter.get_text() == "Line one\\\nline two. Next."


def test_read_span_paragraph_ids_restore_paragraph_identity(reader, git_repo):
    body = (
        '<span data-par-id="par-1">\nFirst sentence.\nSecond sentence.\n</span>\n\n' '<span data-par-id="par-2">\nThird sentence.\n</span>'
    )
    _write_snapshot(git_repo, chapter_id="c-nnn", title="T", body=body)

    chapter = reader.read_chapter("c-nnn")

    assert len(chapter.paragraphs) == 2
    first, second = chapter.paragraphs
    assert first.id == "par-1"
    assert second.id == "par-2"
    assert [s.text for s in first.sentences] == ["First sentence.\n", "Second sentence."]
    assert second.sentences[0].text == "Third sentence."
    # Sentences carry no id in the format; they get freshly generated ones
    for sentence in [*first.sentences, *second.sentences]:
        uuid.UUID(sentence.id)


def test_read_mid_sentence_newline_inside_span_is_ordinary_whitespace(reader, git_repo):
    body = '<span data-par-id="par-1">\nFirst\nline. Still first.\n</span>'
    _write_snapshot(git_repo, chapter_id="c-ooo", title="T", body=body)

    chapter = reader.read_chapter("c-ooo")

    paragraph = chapter.paragraphs[0]
    assert paragraph.get_text() == "First\nline. Still first."
    assert [s.text for s in paragraph.sentences] == ["First\nline. ", "Still first."]


def test_read_unescapes_span_content(reader, git_repo):
    body = '<span data-par-id="par-1">' + "A &lt;span&gt; tag &amp; &quot;quotes&quot;.</span>"
    _write_snapshot(git_repo, chapter_id="c-ppp", title="T", body=body)

    chapter = reader.read_chapter("c-ppp")

    assert chapter.paragraphs[0].sentences[0].text == 'A <span> tag & "quotes".'


def test_read_mixed_spans_and_plain_text(reader, git_repo):
    body = '<span data-par-id="par-1">\nSpan one.\n</span>\nPlain two. Plain three.'
    _write_snapshot(git_repo, chapter_id="c-qqq", title="T", body=body)

    chapter = reader.read_chapter("c-qqq")

    paragraph = chapter.paragraphs[0]
    assert len(paragraph.sentences) == 3
    assert paragraph.id == "par-1"
    assert paragraph.sentences[0].text == "Span one.\n"
    # The span-free text is NLP-split and given fresh ids
    assert paragraph.sentences[1].text.strip() == "Plain two."
    assert paragraph.sentences[2].text.strip() == "Plain three."
    assert paragraph.sentences[1].id != paragraph.sentences[2].id


def test_read_span_bodies_become_fresh_id_sentences(reader, git_repo):
    body = "<span>One.</span>\n<span>Two.</span>"
    _write_snapshot(git_repo, chapter_id="c-rrr", title="T", body=body)

    chapter = reader.read_chapter("c-rrr")

    paragraph = chapter.paragraphs[0]
    assert [s.text for s in paragraph.sentences] == ["One.\n", "Two."]
    assert paragraph.sentences[0].id != paragraph.sentences[1].id
    uuid.UUID(paragraph.sentences[0].id)
    uuid.UUID(paragraph.sentences[1].id)
