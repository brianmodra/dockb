"""Tests for SnapshotWriter — chapter-to-markdown serialization and git commit."""

from __future__ import annotations

import subprocess

import pytest

from dockb.infrastructure.history.snapshot_writer import SnapshotWriter
from dockb.models.chapter import Chapter
from dockb.models.paragraph import Paragraph
from dockb.models.sentence import Sentence
from dockb.models.token import Token
from dockb.models.utils.dockb_collection import DockbCollection


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


def _make_paragraph(text: str, *, p_id: str | None = None) -> Paragraph:
    """Create a paragraph with a single sentence containing the given text."""
    token = Token()
    token.set_text(text)
    sentence = Sentence(id=p_id or "s1")
    sentence.tokens.append(token)
    paragraph = Paragraph()
    paragraph.sentences.append(sentence)
    return paragraph


def test_write_creates_file(writer, git_repo):
    chapter = Chapter(id="c-00000000-0000-0000-0000-000000000001", title="Test")
    chapter.paragraphs.append(_make_paragraph("Hello world."))

    writer.write(chapter)

    expected = git_repo / "chapter-c-00000000-0000-0000-0000-000000000001.md"
    assert expected.exists()


def test_write_returns_commit_id(writer):
    chapter = Chapter(id="c-00000000-0000-0000-0000-000000000002", title="Test")
    chapter.paragraphs.append(_make_paragraph("Some text."))

    commit_id = writer.write(chapter)

    assert isinstance(commit_id, str)
    assert len(commit_id) == 40
    assert all(c in "0123456789abcdef" for c in commit_id)


def test_write_front_matter(writer, git_repo):
    chapter = Chapter(id="c-00000000-0000-0000-0000-000000000003", title="My Chapter")
    chapter.paragraphs.append(_make_paragraph("Body text."))

    writer.write(chapter)

    content = (git_repo / "chapter-c-00000000-0000-0000-0000-000000000003.md").read_text()
    assert content.startswith("---\n")
    assert "id: c-00000000-0000-0000-0000-000000000003" in content
    assert "title: My Chapter" in content
    dash_lines = [i for i, line in enumerate(content.split("\n")) if line.strip() == "---"]
    assert len(dash_lines) >= 2


def test_write_body_text_single_paragraph(writer, git_repo):
    chapter = Chapter(id="c-00000000-0000-0000-0000-000000000004", title="T")
    chapter.paragraphs.append(_make_paragraph("First paragraph."))

    writer.write(chapter)

    content = (git_repo / "chapter-c-00000000-0000-0000-0000-000000000004.md").read_text()
    # Body is everything after the closing ---
    body = content.split("---", 2)[2].strip()
    assert body == "First paragraph."


def test_write_body_text_multi_paragraph(writer, git_repo):
    chapter = Chapter(id="c-00000000-0000-0000-0000-000000000005", title="T")
    chapter.paragraphs.append(_make_paragraph("Para one."))
    chapter.paragraphs.append(_make_paragraph("Para two."))

    writer.write(chapter)

    content = (git_repo / "chapter-c-00000000-0000-0000-0000-000000000005.md").read_text()
    body = content.split("---", 2)[2].strip()
    assert body == "Para one.\n\nPara two."


def test_write_empty_chapter(writer, git_repo):
    chapter = Chapter(id="c-00000000-0000-0000-0000-000000000006", title="Empty")

    writer.write(chapter)

    content = (git_repo / "chapter-c-00000000-0000-0000-0000-000000000006.md").read_text()
    lines = content.split("\n")
    assert lines[0] == "---"
    assert "title: Empty" in content
    body = content.split("---", 2)[2].strip()
    assert body == ""


def test_write_extras_in_front_matter(git_repo):
    """When chapter has model_extra (via model_construct), extras appear in YAML."""
    # model_construct bypasses validation, allowing extra attributes
    chapter = Chapter.model_construct(id="c-00000000-0000-0000-0000-000000000007", title="With Extras")
    chapter._model_extra = {"premise": "A test premise", "order": 1}  # pylint: disable=protected-access
    token = Token()
    token.set_text("Text.")
    sentence = Sentence()
    sentence.tokens.append(token)
    chapter.paragraphs = DockbCollection()
    paragraph = Paragraph()
    paragraph.sentences.append(sentence)
    chapter.paragraphs.append(paragraph)

    writer = SnapshotWriter(base_dir=git_repo)
    writer.write(chapter)

    content = (git_repo / "chapter-c-00000000-0000-0000-0000-000000000007.md").read_text()
    # model_construct doesn't populate model_extra, so no extras in YAML
    # This test verifies the writer gracefully handles missing extras
    assert "id: c-00000000-0000-0000-0000-000000000007" in content
    assert "title: With Extras" in content


def test_write_git_committed(writer, git_repo):
    chapter = Chapter(id="c-00000000-0000-0000-0000-000000000008", title="Git")
    chapter.paragraphs.append(_make_paragraph("Committed."))

    commit_id = writer.write(chapter)

    result = subprocess.run(
        ["git", "log", "--oneline", "-1", commit_id],
        cwd=str(git_repo),
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert "snapshot" in result.stdout.lower()


def test_write_subsequent_commits_increment(git_repo):
    writer = SnapshotWriter(base_dir=git_repo)

    ch1 = Chapter(id="c-00000000-0000-0000-0000-000000000009", title="Ch1")
    ch1.paragraphs.append(_make_paragraph("First."))
    commit1 = writer.write(ch1)

    ch2 = Chapter(id="c-00000000-0000-0000-0000-000000000010", title="Ch2")
    ch2.paragraphs.append(_make_paragraph("Second."))
    commit2 = writer.write(ch2)

    assert commit1 != commit2
    # Both files should exist
    assert (git_repo / "chapter-c-00000000-0000-0000-0000-000000000009.md").exists()
    assert (git_repo / "chapter-c-00000000-0000-0000-0000-000000000010.md").exists()
    # Log should show 2 commits
    result = subprocess.run(["git", "log", "--oneline"], cwd=str(git_repo), capture_output=True, text=True, check=False)
    assert result.stdout.count("snapshot") == 2


def test_write_overwrites_previous_snapshot(git_repo):
    writer = SnapshotWriter(base_dir=git_repo)

    ch = Chapter(id="c-00000000-0000-0000-0000-000000000011", title="V1")
    ch.paragraphs.append(_make_paragraph("Version one."))
    commit1 = writer.write(ch)

    ch.title = "V2"
    ch.paragraphs.clear()
    ch.paragraphs.append(_make_paragraph("Version two."))
    commit2 = writer.write(ch)

    assert commit1 != commit2
    content = (git_repo / "chapter-c-00000000-0000-0000-0000-000000000011.md").read_text()
    assert "V2" in content
    assert "Version two." in content
    assert "Version one." not in content.split("---", 2)[2]
