"""Tests for DocumentStore — the server-owned, id-keyed markdown file tree."""

from __future__ import annotations

import subprocess

import pytest

from dockb.infrastructure.document_store.store import DocumentMetadata, DocumentStore

_SAFE_ID = "d-00000000-0000-0000-0000-000000000001"
_SAFE_CHAPTER = "c-00000000-0000-0000-0000-000000000001"


@pytest.fixture()
def store(tmp_path):
    return DocumentStore(base_dir=tmp_path)


@pytest.fixture()
def git_store(tmp_path):
    subprocess.run(["git", "init"], cwd=str(tmp_path), check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=str(tmp_path), check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=str(tmp_path), check=True, capture_output=True)
    return DocumentStore(base_dir=tmp_path)


def test_document_dir_nested_under_base(store, tmp_path):
    assert store.document_dir(_SAFE_ID) == tmp_path / _SAFE_ID


def test_metadata_file_path(store, tmp_path):
    assert store.metadata_file(_SAFE_ID) == tmp_path / _SAFE_ID / "document_metadata.yaml"


def test_chapter_file_path(store, tmp_path):
    expected = tmp_path / _SAFE_ID / f"chapter-{_SAFE_CHAPTER}.md"
    assert store.chapter_file(_SAFE_ID, _SAFE_CHAPTER) == expected


@pytest.mark.parametrize(
    "bad_id",
    [
        "",
        ".",
        "..",
        "../escape",
        "a/b",
        "a/b/c",
        "..\\escape",
        "dir\\file",
        "/etc/passwd",
        "a\x00b",
        "a\nb",
    ],
)
def test_path_traversal_ids_rejected(store, bad_id, tmp_path):
    for method, args in [
        (store.document_dir, (bad_id,)),
        (store.metadata_file, (bad_id,)),
        (store.chapter_file, (bad_id, _SAFE_CHAPTER)),
        (store.chapter_file, (_SAFE_ID, bad_id)),
    ]:
        with pytest.raises(ValueError, match="not a valid id"):
            method(*args)
    entries_before = set(tmp_path.iterdir())
    assert set(tmp_path.iterdir()) == entries_before


def test_id_with_forward_separator_rejected(store):
    with pytest.raises(ValueError):
        store.document_dir("a/b")


def test_write_and_read_metadata_roundtrip(store):
    store.write_metadata(_SAFE_ID, DocumentMetadata(title="Title", author="Author"))
    metadata = store.read_metadata(_SAFE_ID)
    assert metadata == DocumentMetadata(title="Title", author="Author")


def test_read_metadata_missing_returns_none(store):
    assert store.read_metadata(_SAFE_ID) is None


def test_write_metadata_preserves_existing_keys(store, tmp_path):
    store.write_metadata(_SAFE_ID, DocumentMetadata(title="Title", author="Author"))
    metadata_path = tmp_path / _SAFE_ID / "document_metadata.yaml"
    existing = metadata_path.read_text()
    metadata_path.write_text(existing + "isbn: 123\n")
    store.write_metadata(_SAFE_ID, DocumentMetadata(title="Renamed", author="Author"))
    content = metadata_path.read_text()
    assert "isbn: 123" in content
    metadata = store.read_metadata(_SAFE_ID)
    assert metadata.title == "Renamed"


def test_write_chapter_creates_nested_dirs(store, tmp_path):
    store.write_chapter(_SAFE_ID, _SAFE_CHAPTER, "# Body\n")
    file_path = tmp_path / _SAFE_ID / f"chapter-{_SAFE_CHAPTER}.md"
    assert file_path.is_file()
    assert file_path.read_text() == "# Body\n"


def test_read_chapter_missing_returns_none(store):
    assert store.read_chapter(_SAFE_ID, _SAFE_CHAPTER) is None


def test_read_chapter_after_write(store):
    store.write_chapter(_SAFE_ID, _SAFE_CHAPTER, "abc")
    assert store.read_chapter(_SAFE_ID, _SAFE_CHAPTER) == "abc"


def test_chapter_exists(store):
    assert not store.chapter_exists(_SAFE_ID, _SAFE_CHAPTER)
    store.write_chapter(_SAFE_ID, _SAFE_CHAPTER, "abc")
    assert store.chapter_exists(_SAFE_ID, _SAFE_CHAPTER)


def test_document_exists(store):
    assert not store.document_exists(_SAFE_ID)
    store.write_metadata(_SAFE_ID, DocumentMetadata(title="T", author="A"))
    assert store.document_exists(_SAFE_ID)


def test_list_chapter_files_sorted(store):
    store.write_chapter(_SAFE_ID, "b", "b")
    store.write_chapter(_SAFE_ID, "a", "a")
    files = store.list_chapter_files(_SAFE_ID)
    assert [f.name for f in files] == ["chapter-a.md", "chapter-b.md"]


def test_list_chapter_files_ignores_metadata(store):
    store.write_metadata(_SAFE_ID, DocumentMetadata(title="T", author="A"))
    store.write_chapter(_SAFE_ID, "a", "a")
    assert [f.name for f in store.list_chapter_files(_SAFE_ID)] == ["chapter-a.md"]


def test_from_env_uses_dockb_chapters_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("DOCKB_CHAPTERS_DIR", str(tmp_path))
    store = DocumentStore.from_env()
    assert store.document_dir(_SAFE_ID) == tmp_path / _SAFE_ID


def test_from_env_raises_when_unset(monkeypatch):
    monkeypatch.delenv("DOCKB_CHAPTERS_DIR", raising=False)
    with pytest.raises(ValueError, match="DOCKB_CHAPTERS_DIR"):
        DocumentStore.from_env()


def test_git_commit_records_added_files(git_store, tmp_path):
    git_store.write_chapter(_SAFE_ID, _SAFE_CHAPTER, "# body\n")
    git_store.git_commit(_SAFE_ID, "materialize: doc")
    result = subprocess.run(
        ["git", "log", "--format=%H"],
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert result.stdout.strip()


def test_git_commit_only_commits_the_document_dir(git_store, tmp_path):
    other = DocumentStore(base_dir=tmp_path)
    other.write_chapter("d-other", "c-other", "# other\n")
    git_store.write_chapter(_SAFE_ID, _SAFE_CHAPTER, "# mine\n")
    git_store.git_commit(_SAFE_ID, "materialize: doc")
    staged = subprocess.run(
        ["git", "ls-tree", "-r", "--name-only", "HEAD"],
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
        check=False,
    )
    assert staged.stdout.strip().splitlines() == [_SAFE_ID + "/chapter-c-00000000-0000-0000-0000-000000000001.md"]
    assert "d-other" not in staged.stdout


def test_git_commit_tolerates_unrelated_untracked_files_when_nothing_staged(git_store, tmp_path):
    (tmp_path / "dockb_app.db").write_text("sqlite", encoding="utf-8")
    git_store.write_chapter(_SAFE_ID, _SAFE_CHAPTER, "# body\n")
    git_store.git_commit(_SAFE_ID, "materialize: chapter")
    git_store.git_commit(_SAFE_ID, "open: chapter")

    result = subprocess.run(
        ["git", "log", "--format=%s"],
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
        check=False,
    )
    assert "open: chapter" not in result.stdout
    assert "dockb_app.db" not in result.stdout


@pytest.mark.parametrize("bad_id", ["", ".", "..", "../escape", "a/b", "/etc/passwd"])
def test_git_commit_rejects_invalid_ids(git_store, bad_id):
    with pytest.raises(ValueError, match="not a valid id"):
        git_store.git_commit(bad_id, "message")
