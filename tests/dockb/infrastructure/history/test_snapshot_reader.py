"""Tests for SnapshotReader — markdown-to-chapter deserialization."""

from __future__ import annotations

import subprocess

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
def reader(git_repo):
    return SnapshotReader(base_dir=git_repo)


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


def test_read_paragraphs_are_dirty(reader, git_repo):
    _write_snapshot(git_repo, chapter_id="c-fff", title="T", body="Dirty text.")
    chapter = reader.read_chapter("c-fff")
    assert len(chapter.paragraphs) == 1
    assert chapter.paragraphs[0].dirty is True
    assert chapter.paragraphs[0].text == "Dirty text."


def test_read_raw_content(reader, git_repo):
    _write_snapshot(git_repo, chapter_id="c-ggg", title="T", body="Raw content.")
    content = reader.read("c-ggg")
    assert 'id: "c-ggg"' in content
    assert "Raw content." in content


def test_read_missing_file_raises(reader):
    with pytest.raises(SnapshotError):
        reader.read_chapter("c-nonexistent")


def test_read_at_commit(reader, git_repo):  # pylint: disable=too-many-locals
    from dockb.models.chapter import Chapter
    from dockb.models.paragraph import Paragraph
    from dockb.models.sentence import Sentence
    from dockb.models.token import Token

    writer = SnapshotWriter(base_dir=git_repo)

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
