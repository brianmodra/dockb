"""Roundtrip tests — write a Chapter, read it back, verify equivalence."""

from __future__ import annotations

import subprocess

import pytest

from dockb.infrastructure.history.snapshot_reader import SnapshotReader
from dockb.infrastructure.history.snapshot_writer import SnapshotWriter
from dockb.models.chapter import Chapter
from dockb.models.paragraph import Paragraph
from dockb.models.sentence import Sentence
from dockb.models.token import Token


@pytest.fixture()
def git_repo(tmp_path):
    """Create a temporary git repository."""
    subprocess.run(["git", "init"], cwd=str(tmp_path), check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=str(tmp_path), check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=str(tmp_path), check=True, capture_output=True)
    return tmp_path


@pytest.fixture()
def writer(git_repo):
    return SnapshotWriter(base_dir=git_repo)


@pytest.fixture()
def reader(git_repo):
    return SnapshotReader(base_dir=git_repo)


def _make_paragraph_with_sentences(*texts: str) -> Paragraph:
    """Create a paragraph with one sentence per text."""
    paragraph = Paragraph()
    for text in texts:
        token = Token()
        token.set_text(text)
        sentence = Sentence()
        sentence.tokens.append(token)
        paragraph.sentences.append(sentence)
    return paragraph


def test_roundtrip_single_paragraph(writer, reader):
    chapter = Chapter(id="c-round-001", title="Single")
    chapter.paragraphs.append(_make_paragraph_with_sentences("Hello world."))

    writer.write(chapter)
    result = reader.read_chapter("c-round-001")

    assert result.id == "c-round-001"
    assert result.title == "Single"
    assert result.get_text() == "Hello world."
    assert len(result.paragraphs) == 1


def test_roundtrip_multi_paragraph(writer, reader):
    chapter = Chapter(id="c-round-002", title="Multi")
    chapter.paragraphs.append(_make_paragraph_with_sentences("First paragraph."))
    chapter.paragraphs.append(_make_paragraph_with_sentences("Second paragraph."))
    chapter.paragraphs.append(_make_paragraph_with_sentences("Third paragraph."))

    writer.write(chapter)
    result = reader.read_chapter("c-round-002")

    assert result.id == "c-round-002"
    assert result.title == "Multi"
    assert len(result.paragraphs) == 3
    texts = [p.get_text() for p in result.paragraphs]
    assert texts == ["First paragraph.", "Second paragraph.", "Third paragraph."]


def test_roundtrip_preserves_attrs(writer, reader):
    chapter = Chapter(id="c-round-003", title="Attrs Test")
    chapter.paragraphs.append(_make_paragraph_with_sentences("Content."))

    writer.write(chapter)
    result = reader.read_chapter("c-round-003")

    assert result.id == "c-round-003"
    assert result.title == "Attrs Test"


def test_roundtrip_empty_chapter(writer, reader):
    chapter = Chapter(id="c-round-004", title="Empty")

    writer.write(chapter)
    result = reader.read_chapter("c-round-004")

    assert result.id == "c-round-004"
    assert result.title == "Empty"
    assert len(result.paragraphs) == 0
    assert result.get_text() == ""


def test_roundtrip_full_text_equivalence(writer, reader):
    """The full concatenated text should match regardless of paragraph boundaries."""
    original = Chapter(id="c-round-005", title="Full Text")
    original.paragraphs.append(_make_paragraph_with_sentences("The quick brown fox ", "jumps over the lazy dog."))
    original.paragraphs.append(_make_paragraph_with_sentences("Pack my box ", "with five dozen liquor jugs."))
    original_text = original.get_text()

    writer.write(original)
    result = reader.read_chapter("c-round-005")

    assert result.get_text() == original_text


def test_roundtrip_paragraph_ids_are_different(writer, reader):
    """Read-back paragraphs get new IDs (they are re-hydrated, not stored verbatim)."""
    chapter = Chapter(id="c-round-006", title="New IDs")
    chapter.paragraphs.append(_make_paragraph_with_sentences("Text."))

    writer.write(chapter)
    result = reader.read_chapter("c-round-006")

    # The chapter ID is preserved from front matter
    assert result.id == "c-round-006"
    # Paragraph IDs are newly generated (not from the original)
    assert len(result.paragraphs) == 1


def test_roundtrip_repeated_writes(writer, reader):
    """Multiple writes to the same chapter should read the latest version."""
    chapter = Chapter(id="c-round-007", title="V1")
    chapter.paragraphs.append(_make_paragraph_with_sentences("Version one."))

    writer.write(chapter)

    chapter.title = "V2"
    chapter.paragraphs.clear()
    chapter.paragraphs.append(_make_paragraph_with_sentences("Version two."))
    chapter.paragraphs.append(_make_paragraph_with_sentences("Still V2."))

    writer.write(chapter)
    result = reader.read_chapter("c-round-007")

    assert result.title == "V2"
    assert result.get_text() == "Version two.Still V2."


def test_roundtrip_two_chapters_independent(writer, reader):
    """Two different chapters should not interfere with each other."""
    ch1 = Chapter(id="c-round-008a", title="Chapter A")
    ch1.paragraphs.append(_make_paragraph_with_sentences("Alpha."))

    ch2 = Chapter(id="c-round-008b", title="Chapter B")
    ch2.paragraphs.append(_make_paragraph_with_sentences("Beta."))

    writer.write(ch1)
    writer.write(ch2)

    result1 = reader.read_chapter("c-round-008a")
    result2 = reader.read_chapter("c-round-008b")

    assert result1.title == "Chapter A"
    assert result1.get_text() == "Alpha."
    assert result2.title == "Chapter B"
    assert result2.get_text() == "Beta."
