"""Tests for DocumentStore — the server-owned, title/act-keyed markdown file tree."""

from __future__ import annotations

import subprocess

import pytest

from dockb.infrastructure.document_store.store import DocumentMetadata, DocumentStore

_SAFE_TITLE = "Linchpin"
_SAFE_CHAPTER = "Opening 1"


@pytest.fixture()
def store(tmp_path):
    return DocumentStore(base_dir=tmp_path)


@pytest.fixture()
def git_store(tmp_path):
    subprocess.run(["git", "init"], cwd=str(tmp_path), check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=str(tmp_path), check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=str(tmp_path), check=True, capture_output=True)
    return DocumentStore(base_dir=tmp_path)


def test_document_dir_uses_title(store, tmp_path):
    assert store.document_dir(_SAFE_TITLE) == tmp_path / _SAFE_TITLE


def test_metadata_file_path(store, tmp_path):
    assert store.metadata_file(_SAFE_TITLE) == tmp_path / _SAFE_TITLE / "document_metadata.yaml"


def test_act_dir_uses_act_none_for_empty(store, tmp_path):
    assert store.act_dir(_SAFE_TITLE, "") == tmp_path / _SAFE_TITLE / "Act None"


def test_act_dir_uses_act_verbatim_when_prefixed(store, tmp_path):
    assert store.act_dir(_SAFE_TITLE, "Act I") == tmp_path / _SAFE_TITLE / "Act I"


def test_act_dir_prefixes_bare_act_name(store, tmp_path):
    assert store.act_dir(_SAFE_TITLE, "I") == tmp_path / _SAFE_TITLE / "Act I"


def test_chapter_file_path_under_act_dir(store, tmp_path):
    expected = tmp_path / _SAFE_TITLE / "Act I" / f"{_SAFE_CHAPTER}.md"
    assert store.chapter_file(_SAFE_TITLE, "Act I", _SAFE_CHAPTER) == expected


def test_chapter_file_without_act_goes_under_act_none(store, tmp_path):
    expected = tmp_path / _SAFE_TITLE / "Act None" / f"{_SAFE_CHAPTER}.md"
    assert store.chapter_file(_SAFE_TITLE, "", _SAFE_CHAPTER) == expected


@pytest.mark.parametrize(
    "bad_title",
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
        "a\bb",
        "a\x7fb",
    ],
)
def test_path_traversal_titles_rejected(store, bad_title):
    for method, args in [
        (store.document_dir, (bad_title,)),
        (store.metadata_file, (bad_title,)),
        (store.act_dir, (bad_title, "Act I")),
        (store.chapter_file, (bad_title, "Act I", _SAFE_CHAPTER)),
        (store.chapter_file, (_SAFE_TITLE, "Act I", bad_title)),
    ]:
        with pytest.raises(ValueError, match="not a valid title"):
            method(*args)


@pytest.mark.parametrize(
    "bad_act",
    [
        "../escape",
        "Act ../escape",
        "Act ../../x",
        "a/b",
        "Act ..\\x",
        "Act /abs",
    ],
)
def test_path_traversal_acts_rejected(store, bad_act):
    with pytest.raises(ValueError, match="not a valid title"):
        store.act_dir(_SAFE_TITLE, bad_act)
    with pytest.raises(ValueError, match="not a valid title"):
        store.chapter_file(_SAFE_TITLE, bad_act, _SAFE_CHAPTER)


def test_write_and_read_metadata_roundtrip(store):
    store.write_metadata(_SAFE_TITLE, DocumentMetadata(title="Linchpin", author="Author"))
    metadata = store.read_metadata(_SAFE_TITLE)
    assert metadata == DocumentMetadata(title="Linchpin", author="Author")


def test_read_metadata_missing_returns_none(store):
    assert store.read_metadata(_SAFE_TITLE) is None


def test_write_metadata_preserves_existing_keys(store, tmp_path):
    store.write_metadata(_SAFE_TITLE, DocumentMetadata(title="Linchpin", author="Author"))
    metadata_path = tmp_path / _SAFE_TITLE / "document_metadata.yaml"
    existing = metadata_path.read_text()
    metadata_path.write_text(existing + "isbn: 123\n")
    store.write_metadata(_SAFE_TITLE, DocumentMetadata(title="Renamed", author="Author"))
    content = metadata_path.read_text()
    assert "isbn: 123" in content
    metadata = store.read_metadata(_SAFE_TITLE)
    assert metadata.title == "Renamed"


def test_write_chapter_creates_act_dir(store, tmp_path):
    store.write_chapter(_SAFE_TITLE, "", _SAFE_CHAPTER, "# Body\n")
    file_path = tmp_path / _SAFE_TITLE / "Act None" / f"{_SAFE_CHAPTER}.md"
    assert file_path.is_file()
    assert file_path.read_text() == "# Body\n"


def test_read_chapter_missing_returns_none(store):
    assert store.read_chapter(_SAFE_TITLE, "Act I", _SAFE_CHAPTER) is None


def test_read_chapter_after_write(store):
    store.write_chapter(_SAFE_TITLE, "Act I", _SAFE_CHAPTER, "abc")
    assert store.read_chapter(_SAFE_TITLE, "Act I", _SAFE_CHAPTER) == "abc"


def test_chapter_exists(store):
    assert not store.chapter_exists(_SAFE_TITLE, "Act I", _SAFE_CHAPTER)
    store.write_chapter(_SAFE_TITLE, "Act I", _SAFE_CHAPTER, "abc")
    assert store.chapter_exists(_SAFE_TITLE, "Act I", _SAFE_CHAPTER)


def test_document_exists(store):
    assert not store.document_exists(_SAFE_TITLE)
    store.write_metadata(_SAFE_TITLE, DocumentMetadata(title="T", author="A"))
    assert store.document_exists(_SAFE_TITLE)


def test_list_chapter_files_recurses_act_dirs_sorted(store):
    store.write_chapter(_SAFE_TITLE, "Act II", "b", "b")
    store.write_chapter(_SAFE_TITLE, "Act I", "a", "a")
    files = store.list_chapter_files(_SAFE_TITLE)
    assert [str(f.relative_to(store.document_dir(_SAFE_TITLE))) for f in files] == [
        "Act I/a.md",
        "Act II/b.md",
    ]


def test_list_chapter_files_ignores_metadata(store):
    store.write_metadata(_SAFE_TITLE, DocumentMetadata(title="T", author="A"))
    store.write_chapter(_SAFE_TITLE, "", "a", "a")
    assert [f.name for f in store.list_chapter_files(_SAFE_TITLE)] == ["a.md"]


def test_from_env_uses_dockb_chapters_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("DOCKB_CHAPTERS_DIR", str(tmp_path))
    store = DocumentStore.from_env()
    assert store.document_dir(_SAFE_TITLE) == tmp_path / _SAFE_TITLE


def test_from_env_raises_when_unset(monkeypatch):
    monkeypatch.delenv("DOCKB_CHAPTERS_DIR", raising=False)
    with pytest.raises(ValueError, match="DOCKB_CHAPTERS_DIR"):
        DocumentStore.from_env()


def test_git_commit_records_added_files(git_store, tmp_path):
    git_store.write_chapter(_SAFE_TITLE, "", _SAFE_CHAPTER, "# body\n")
    git_store.git_commit(_SAFE_TITLE, "materialize: doc")
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
    other.write_chapter("Other", "", "other", "# other\n")
    git_store.write_chapter(_SAFE_TITLE, "", _SAFE_CHAPTER, "# mine\n")
    git_store.git_commit(_SAFE_TITLE, "materialize: doc")
    staged = subprocess.run(
        ["git", "ls-tree", "-r", "--name-only", "HEAD"],
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
        check=False,
    )
    assert staged.stdout.strip().splitlines() == ["Linchpin/Act None/Opening 1.md"]
    assert "Other" not in staged.stdout


def test_git_commit_tolerates_unrelated_untracked_files_when_nothing_staged(git_store, tmp_path):
    (tmp_path / "dockb_app.db").write_text("sqlite", encoding="utf-8")
    git_store.write_chapter(_SAFE_TITLE, "", _SAFE_CHAPTER, "# body\n")
    git_store.git_commit(_SAFE_TITLE, "materialize: chapter")
    git_store.git_commit(_SAFE_TITLE, "open: chapter")

    result = subprocess.run(
        ["git", "log", "--format=%s"],
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
        check=False,
    )
    assert "open: chapter" not in result.stdout
    assert "dockb_app.db" not in result.stdout


@pytest.mark.parametrize("bad_title", ["", ".", "..", "../escape", "a/b", "/etc/passwd"])
def test_git_commit_rejects_invalid_titles(git_store, bad_title):
    with pytest.raises(ValueError, match="not a valid title"):
        git_store.git_commit(bad_title, "message")
