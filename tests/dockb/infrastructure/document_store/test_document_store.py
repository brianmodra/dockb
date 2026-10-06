"""Tests for DocumentStore — the server-owned, account/act-keyed markdown file tree."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from pydantic import ValidationError

from dockb.controllers.schemas.documents import DocumentAttrs
from dockb.exceptions import SnapshotError
from dockb.infrastructure.document_store.factory import DocumentStoreFactory
from dockb.infrastructure.document_store.store import DocumentMetadata, DocumentStore

_SAFE_TITLE = "Linchpin"
_SAFE_CHAPTER = "Opening 1"
_ACCOUNT = "acct-1"
_OTHER_ACCOUNT = "acct-2"


@pytest.fixture()
def git_identity(monkeypatch):
    """Give git a commit identity without a repository or the machine's own config.

    Each account directory is its own repository, created on first use, so a test
    cannot pre-configure one with ``git config``. The environment variables apply to
    every repository git creates below, which keeps these tests independent of whether
    the machine running them has a global identity.
    """
    monkeypatch.setenv("GIT_AUTHOR_NAME", "Test")
    monkeypatch.setenv("GIT_AUTHOR_EMAIL", "test@test.com")
    monkeypatch.setenv("GIT_COMMITTER_NAME", "Test")
    monkeypatch.setenv("GIT_COMMITTER_EMAIL", "test@test.com")


@pytest.fixture()
def store(tmp_path, git_identity):  # pylint: disable=unused-argument
    return DocumentStore(base_dir=tmp_path, account_id=_ACCOUNT)


@pytest.fixture()
def other_store(tmp_path, git_identity):  # pylint: disable=unused-argument
    """A second account's store over the same base directory."""
    return DocumentStore(base_dir=tmp_path, account_id=_OTHER_ACCOUNT)


@pytest.fixture()
def git_store(tmp_path, git_identity):  # pylint: disable=unused-argument
    """A store whose account repository already exists, with no commits in it.

    ``git_commit`` provisions the repository before deciding whether there is
    anything to stage, so committing a document that has no files yet sets up the
    repository and leaves HEAD empty — which is the state these tests want to
    observe a first commit from.
    """
    store = DocumentStore(base_dir=tmp_path, account_id=_ACCOUNT)
    store.git_commit(_SAFE_TITLE, "provision repo")
    return store


def test_document_dir_uses_title_under_the_account_dir(store, tmp_path):
    assert store.document_dir(_SAFE_TITLE) == tmp_path / _ACCOUNT / _SAFE_TITLE


def test_metadata_file_path(store, tmp_path):
    assert store.metadata_file(_SAFE_TITLE) == tmp_path / _ACCOUNT / _SAFE_TITLE / "document_metadata.yaml"


def test_act_dir_uses_act_none_for_empty(store, tmp_path):
    assert store.act_dir(_SAFE_TITLE, "") == tmp_path / _ACCOUNT / _SAFE_TITLE / "Act None"


def test_act_dir_uses_act_verbatim_when_prefixed(store, tmp_path):
    assert store.act_dir(_SAFE_TITLE, "Act I") == tmp_path / _ACCOUNT / _SAFE_TITLE / "Act I"


def test_act_dir_prefixes_bare_act_name(store, tmp_path):
    assert store.act_dir(_SAFE_TITLE, "I") == tmp_path / _ACCOUNT / _SAFE_TITLE / "Act I"


def test_chapter_file_path_under_act_dir(store, tmp_path):
    expected = tmp_path / _ACCOUNT / _SAFE_TITLE / "Act I" / f"{_SAFE_CHAPTER}.md"
    assert store.chapter_file(_SAFE_TITLE, "Act I", _SAFE_CHAPTER) == expected


def test_chapter_file_without_act_goes_under_act_none(store, tmp_path):
    expected = tmp_path / _ACCOUNT / _SAFE_TITLE / "Act None" / f"{_SAFE_CHAPTER}.md"
    assert store.chapter_file(_SAFE_TITLE, "", _SAFE_CHAPTER) == expected


def test_chapter_file_character_category_goes_under_characters_dir(store, tmp_path):
    expected = tmp_path / _ACCOUNT / _SAFE_TITLE / "Characters" / f"{_SAFE_CHAPTER}.md"
    assert store.chapter_file(_SAFE_TITLE, "", _SAFE_CHAPTER, category="Character") == expected


def test_chapter_file_character_category_ignores_act(store, tmp_path):
    expected = tmp_path / _ACCOUNT / _SAFE_TITLE / "Characters" / f"{_SAFE_CHAPTER}.md"
    assert store.chapter_file(_SAFE_TITLE, "Act I", _SAFE_CHAPTER, category="Character") == expected


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


def test_store_agrees_with_the_api_schema_on_every_title(store):
    """The store and the wire schema must reject exactly the same titles.

    A title the API accepts but the store refuses reaches the filesystem as a
    500, and one the store accepts but the API rejects is a contract the editor
    cannot satisfy. Both sides read one rule, so they cannot drift.
    """
    for title in ("Faith", "Book 1: The Beginning", "...", ".hidden", "a/b", "../x", "..", "nul\x00", "a\\b", "del\x7f"):
        try:
            DocumentAttrs(title=title, author="Author")
        except ValidationError:
            api_accepts = False
        else:
            api_accepts = True
        try:
            store.document_dir(title)
        except ValueError:
            store_accepts = False
        else:
            store_accepts = True
        assert api_accepts == store_accepts, f"schema and store disagree about {title!r}"


def test_write_and_read_metadata_roundtrip(store):
    store.write_metadata(_SAFE_TITLE, DocumentMetadata(title="Linchpin", author="Author"))
    metadata = store.read_metadata(_SAFE_TITLE)
    assert metadata == DocumentMetadata(title="Linchpin", author="Author")


def test_read_metadata_missing_returns_none(store):
    assert store.read_metadata(_SAFE_TITLE) is None


def test_write_metadata_preserves_existing_keys(store, tmp_path):
    store.write_metadata(_SAFE_TITLE, DocumentMetadata(title="Linchpin", author="Author"))
    metadata_path = tmp_path / _ACCOUNT / _SAFE_TITLE / "document_metadata.yaml"
    existing = metadata_path.read_text()
    metadata_path.write_text(existing + "isbn: 123\n")
    store.write_metadata(_SAFE_TITLE, DocumentMetadata(title="Renamed", author="Author"))
    content = metadata_path.read_text()
    assert "isbn: 123" in content
    metadata = store.read_metadata(_SAFE_TITLE)
    assert metadata.title == "Renamed"


def test_write_chapter_creates_act_dir(store, tmp_path):
    store.write_chapter(_SAFE_TITLE, "", _SAFE_CHAPTER, "# Body\n")
    file_path = tmp_path / _ACCOUNT / _SAFE_TITLE / "Act None" / f"{_SAFE_CHAPTER}.md"
    assert file_path.is_file()
    assert file_path.read_text() == "# Body\n"


def test_write_chapter_character_creates_characters_dir(store, tmp_path):
    store.write_chapter(_SAFE_TITLE, "Act I", _SAFE_CHAPTER, "# Body\n", category="Character")
    file_path = tmp_path / _ACCOUNT / _SAFE_TITLE / "Characters" / f"{_SAFE_CHAPTER}.md"
    assert file_path.is_file()
    assert file_path.read_text() == "# Body\n"
    assert store.chapter_exists(_SAFE_TITLE, "", _SAFE_CHAPTER, category="Character")
    assert store.read_chapter(_SAFE_TITLE, "", _SAFE_CHAPTER, category="Character") == "# Body\n"


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


def test_list_chapter_files_includes_characters_dir_sorted(store):
    store.write_chapter(_SAFE_TITLE, "", "Zeta 2", "b", category="Character")
    store.write_chapter(_SAFE_TITLE, "Act I", "Alpha 1", "a")
    files = store.list_chapter_files(_SAFE_TITLE)
    assert [str(f.relative_to(store.document_dir(_SAFE_TITLE))) for f in files] == [
        "Act I/Alpha 1.md",
        "Characters/Zeta 2.md",
    ]


def test_list_chapter_files_ignores_metadata(store):
    store.write_metadata(_SAFE_TITLE, DocumentMetadata(title="T", author="A"))
    store.write_chapter(_SAFE_TITLE, "", "a", "a")
    assert [f.name for f in store.list_chapter_files(_SAFE_TITLE)] == ["a.md"]


def test_from_env_uses_dockb_chapters_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("DOCKB_CHAPTERS_DIR", str(tmp_path))
    store = DocumentStore.from_env(_ACCOUNT)
    assert store.document_dir(_SAFE_TITLE) == tmp_path / _ACCOUNT / _SAFE_TITLE


def test_from_env_raises_when_unset(monkeypatch):
    monkeypatch.delenv("DOCKB_CHAPTERS_DIR", raising=False)
    with pytest.raises(ValueError, match="DOCKB_CHAPTERS_DIR"):
        DocumentStore.from_env(_ACCOUNT)


def test_git_commit_records_added_files(git_store):
    git_store.write_chapter(_SAFE_TITLE, "", _SAFE_CHAPTER, "# body\n")
    git_store.git_commit(_SAFE_TITLE, "materialize: doc")
    result = subprocess.run(
        ["git", "log", "--format=%H"],
        cwd=str(git_store.account_dir()),
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert result.stdout.strip()


def test_git_commit_only_commits_the_document_dir(git_store):
    git_store.write_chapter(_SAFE_TITLE, "", _SAFE_CHAPTER, "# mine\n")
    git_store.write_chapter("Other", "", "other", "# other\n")
    git_store.git_commit(_SAFE_TITLE, "materialize: doc")
    staged = subprocess.run(
        ["git", "ls-tree", "-r", "--name-only", "HEAD"],
        cwd=str(git_store.account_dir()),
        capture_output=True,
        text=True,
        check=False,
    )
    assert staged.stdout.strip().splitlines() == ["Linchpin/Act None/Opening 1.md"]
    assert "Other" not in staged.stdout


def test_git_commit_tolerates_unrelated_untracked_files_when_nothing_staged(git_store):
    git_store.account_dir().mkdir(parents=True, exist_ok=True)
    (git_store.account_dir() / "dockb_app.db").write_text("sqlite", encoding="utf-8")
    git_store.write_chapter(_SAFE_TITLE, "", _SAFE_CHAPTER, "# body\n")
    git_store.git_commit(_SAFE_TITLE, "materialize: chapter")
    git_store.git_commit(_SAFE_TITLE, "open: chapter")

    result = subprocess.run(
        ["git", "log", "--format=%s"],
        cwd=str(git_store.account_dir()),
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


def _porcelain(store) -> str:
    return subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=str(store.account_dir()),
        capture_output=True,
        text=True,
        check=False,
    ).stdout.strip()


def _log_subjects(store) -> list[str]:
    """Return the account repository's commit subjects, oldest first."""
    return subprocess.run(
        ["git", "log", "--reverse", "--format=%s"],
        cwd=str(store.account_dir()),
        capture_output=True,
        text=True,
        check=True,
    ).stdout.splitlines()


def _other_document_tree(tmp_path, body: str) -> Path:
    """Write a document's directory at the flat pre-ownership path, ``<base>/<title>``.

    Not through a store, because that is the point: no account holds this directory, and
    a ``DocumentStore`` cannot name a path with no account segment in it.
    """
    root = tmp_path / _SAFE_TITLE
    chapter = root / "Act I" / f"{_SAFE_CHAPTER}.md"
    chapter.parent.mkdir(parents=True, exist_ok=True)
    chapter.write_text(body, encoding="utf-8")
    (root / "document_metadata.yaml").write_text(f"title: {_SAFE_TITLE}\nauthor: Test\n", encoding="utf-8")
    return root


def test_remove_document_git_rms_committed_tree(git_store):
    git_store.write_metadata(_SAFE_TITLE, DocumentMetadata(title=_SAFE_TITLE, author="Test"))
    git_store.write_chapter(_SAFE_TITLE, "Act I", _SAFE_CHAPTER, "# body\n")
    git_store.git_commit(_SAFE_TITLE, "materialize: doc")
    assert _porcelain(git_store) == ""

    git_store.remove_document(_SAFE_TITLE)

    assert not git_store.document_exists(_SAFE_TITLE)
    assert _porcelain(git_store) == ""
    log = subprocess.run(
        ["git", "log", "--oneline", "--", _SAFE_TITLE],
        cwd=str(git_store.account_dir()),
        capture_output=True,
        text=True,
        check=False,
    )
    assert any(line.endswith(f"remove: {_SAFE_TITLE}") for line in log.stdout.splitlines())


def test_remove_document_missing_dir_is_noop(git_store):
    git_store.remove_document(_SAFE_TITLE)


def test_remove_chapter_git_rms_file_and_prunes_empty_dirs(git_store):
    git_store.write_chapter(_SAFE_TITLE, "Act I", _SAFE_CHAPTER, "# body\n")
    git_store.write_chapter(_SAFE_TITLE, "Act I", "Setup 9", "# nine\n")
    git_store.git_commit(_SAFE_TITLE, "materialize: doc")

    git_store.remove_chapter(_SAFE_TITLE, "Act I", "Setup 9")

    assert not git_store.chapter_exists(_SAFE_TITLE, "Act I", "Setup 9")
    assert git_store.chapter_exists(_SAFE_TITLE, "Act I", _SAFE_CHAPTER)
    assert git_store.document_exists(_SAFE_TITLE)
    assert _porcelain(git_store) == ""
    log = subprocess.run(
        ["git", "log", "--oneline", "--", _SAFE_TITLE],
        cwd=str(git_store.account_dir()),
        capture_output=True,
        text=True,
        check=False,
    )
    assert any(line.endswith("remove: chapter Setup 9") for line in log.stdout.splitlines())


def test_remove_last_chapter_prunes_document_dir(git_store):
    git_store.write_chapter(_SAFE_TITLE, "Act II", _SAFE_CHAPTER, "# body\n")
    git_store.git_commit(_SAFE_TITLE, "materialize: doc")

    git_store.remove_chapter(_SAFE_TITLE, "Act II", _SAFE_CHAPTER)

    assert not git_store.document_exists(_SAFE_TITLE)


def test_remove_chapter_missing_file_is_noop(git_store):
    git_store.remove_chapter(_SAFE_TITLE, "Act I", "Nope")


def test_remove_character_chapter_prunes_characters_dir(git_store):
    git_store.write_metadata(_SAFE_TITLE, DocumentMetadata(title=_SAFE_TITLE, author="Test"))
    git_store.write_chapter(_SAFE_TITLE, "", "Dramatis 9", "# nine\n", category="Character")
    git_store.write_chapter(_SAFE_TITLE, "", _SAFE_CHAPTER, "# body\n", category="Character")
    git_store.git_commit(_SAFE_TITLE, "materialize: doc")

    git_store.remove_chapter(_SAFE_TITLE, "", "Dramatis 9", category="Character")

    assert not git_store.chapter_exists(_SAFE_TITLE, "", "Dramatis 9", category="Character")
    assert git_store.chapter_exists(_SAFE_TITLE, "", _SAFE_CHAPTER, category="Character")
    assert git_store.document_exists(_SAFE_TITLE)
    assert _porcelain(git_store) == ""


def test_rename_chapter_character_git_mvs_within_characters_dir(git_store):
    git_store.write_chapter(_SAFE_TITLE, "", _SAFE_CHAPTER, "---\ntitle: Opening 1\n---\n\n# body\n", category="Character")
    git_store.git_commit(_SAFE_TITLE, "materialize: doc")

    git_store.rename_chapter(_SAFE_TITLE, "", _SAFE_CHAPTER, "Opening 2", category="Character")

    assert not git_store.chapter_exists(_SAFE_TITLE, "", _SAFE_CHAPTER, category="Character")
    content = git_store.read_chapter(_SAFE_TITLE, "", "Opening 2", category="Character")
    assert content is not None and "title: Opening 2" in content
    assert _porcelain(git_store) == ""


def test_rename_document_git_mvs_dir_and_rewrites_metadata(git_store):
    git_store.write_metadata(_SAFE_TITLE, DocumentMetadata(title=_SAFE_TITLE, author="Test"))
    git_store.write_chapter(_SAFE_TITLE, "Act I", _SAFE_CHAPTER, "# body\n")
    git_store.git_commit(_SAFE_TITLE, "materialize: doc")

    git_store.rename_document(_SAFE_TITLE, "Tome")

    assert not git_store.document_exists(_SAFE_TITLE)
    assert git_store.document_exists("Tome")
    assert git_store.read_metadata("Tome") == DocumentMetadata(title="Tome", author="Test")
    assert git_store.chapter_exists("Tome", "Act I", _SAFE_CHAPTER)
    assert _porcelain(git_store) == ""
    log = subprocess.run(
        ["git", "log", "--oneline"],
        cwd=str(git_store.account_dir()),
        capture_output=True,
        text=True,
        check=False,
    )
    assert any(f"rename: {_SAFE_TITLE} -> Tome" in line for line in log.stdout.splitlines())


def test_rename_document_missing_dir_is_noop(git_store):
    git_store.rename_document(_SAFE_TITLE, "Tome")
    assert not git_store.document_exists("Tome")


def test_rename_document_to_existing_title_raises(git_store):
    git_store.write_metadata(_SAFE_TITLE, DocumentMetadata(title=_SAFE_TITLE, author="A"))
    git_store.write_metadata("Tome", DocumentMetadata(title="Tome", author="B"))
    git_store.git_commit(_SAFE_TITLE, "one")
    git_store.git_commit("Tome", "two")
    with pytest.raises(SnapshotError):
        git_store.rename_document(_SAFE_TITLE, "Tome")


def test_rename_chapter_git_mvs_file_and_rewrites_front_matter(git_store):
    git_store.write_chapter(_SAFE_TITLE, "Act I", _SAFE_CHAPTER, "---\ntitle: Opening 1\n---\n\n# body\n")
    git_store.write_chapter(_SAFE_TITLE, "Act I", "Setup 9", "# nine\n")
    git_store.git_commit(_SAFE_TITLE, "materialize: doc")

    git_store.rename_chapter(_SAFE_TITLE, "Act I", _SAFE_CHAPTER, "Opening 2")

    assert not git_store.chapter_exists(_SAFE_TITLE, "Act I", _SAFE_CHAPTER)
    content = git_store.read_chapter(_SAFE_TITLE, "Act I", "Opening 2")
    assert content is not None and "title: Opening 2" in content
    assert git_store.chapter_exists(_SAFE_TITLE, "Act I", "Setup 9")
    assert _porcelain(git_store) == ""
    log = subprocess.run(
        ["git", "log", "--oneline"],
        cwd=str(git_store.account_dir()),
        capture_output=True,
        text=True,
        check=False,
    )
    assert any(f"rename: chapter {_SAFE_CHAPTER} -> Opening 2" in line for line in log.stdout.splitlines())


def test_rename_chapter_missing_file_is_noop(git_store):
    git_store.rename_chapter(_SAFE_TITLE, "Act I", "Nope", "Nowhere")
    assert not git_store.chapter_exists(_SAFE_TITLE, "Act I", "Nowhere")


# ---------------------------------------------------------------------------
# Per-account scoping
# ---------------------------------------------------------------------------


def test_account_dir_is_the_base_dir_plus_the_account_id(store, tmp_path):
    assert store.account_dir() == tmp_path / _ACCOUNT


def test_constructor_requires_an_account_id(tmp_path):
    with pytest.raises(ValueError, match="account_id"):
        DocumentStore(base_dir=tmp_path, account_id="")


@pytest.mark.parametrize(
    "hostile",
    ["..", ".", "../escape", "a/b", "a\\b", "\u0000", "with\nnewline", "/abs"],
)
def test_constructor_refuses_an_account_id_that_is_not_one_segment(tmp_path, hostile):
    """The account id names a directory, so it is held to the same rule as a title.

    Today every account id is a UUID minted by the accounts store, but the store is
    the boundary that builds paths, and a caller that ever passed a name from a
    request must not be able to walk out of the base directory with it.
    """
    with pytest.raises(ValueError, match="account id"):
        DocumentStore(base_dir=tmp_path, account_id=hostile)


def test_two_accounts_do_not_share_a_document_directory(store, other_store):
    assert store.document_dir(_SAFE_TITLE) != other_store.document_dir(_SAFE_TITLE)


def test_same_title_documents_coexist_across_accounts(store, other_store):
    store.write_chapter(_SAFE_TITLE, "Act I", _SAFE_CHAPTER, "# mine\n")
    other_store.write_chapter(_SAFE_TITLE, "Act I", _SAFE_CHAPTER, "# theirs\n")

    assert store.read_chapter(_SAFE_TITLE, "Act I", _SAFE_CHAPTER) == "# mine\n"
    assert other_store.read_chapter(_SAFE_TITLE, "Act I", _SAFE_CHAPTER) == "# theirs\n"


def test_one_accounts_write_is_invisible_to_the_other(store, other_store):
    store.write_chapter(_SAFE_TITLE, "Act I", _SAFE_CHAPTER, "# mine\n")

    assert not other_store.document_exists(_SAFE_TITLE)
    assert not other_store.chapter_exists(_SAFE_TITLE, "Act I", _SAFE_CHAPTER)


def test_a_commit_provisions_the_account_repository(store):
    store.write_chapter(_SAFE_TITLE, "Act I", _SAFE_CHAPTER, "# body\n")

    assert not (store.account_dir() / ".git").exists()

    store.git_commit(_SAFE_TITLE, "materialize: doc")

    assert (store.account_dir() / ".git").is_dir()


def test_each_account_gets_its_own_repository(store, other_store):
    store.write_chapter(_SAFE_TITLE, "Act I", _SAFE_CHAPTER, "# mine\n")
    store.git_commit(_SAFE_TITLE, "mine")
    other_store.write_chapter("Other", "Act I", "other", "# theirs\n")
    other_store.git_commit("Other", "theirs")

    assert (store.account_dir() / ".git").is_dir()
    assert (other_store.account_dir() / ".git").is_dir()
    assert store.account_dir() != other_store.account_dir()


def test_an_accounts_history_holds_only_its_own_commits(store, other_store):
    store.write_chapter(_SAFE_TITLE, "Act I", _SAFE_CHAPTER, "# mine\n")
    store.git_commit(_SAFE_TITLE, "mine one")
    store.write_chapter(_SAFE_TITLE, "Act II", "Second 2", "# more\n")
    store.git_commit(_SAFE_TITLE, "mine two")
    other_store.write_chapter("Other", "Act I", "other", "# theirs\n")
    other_store.git_commit("Other", "theirs")

    mine = subprocess.run(
        ["git", "log", "--format=%s"],
        cwd=str(store.account_dir()),
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    theirs = subprocess.run(
        ["git", "log", "--format=%s"],
        cwd=str(other_store.account_dir()),
        capture_output=True,
        text=True,
        check=True,
    ).stdout

    assert "mine one" in mine and "mine two" in mine
    assert "theirs" not in mine
    assert "theirs" in theirs
    assert "mine one" not in theirs


def test_a_commit_never_carries_another_accounts_files(store, other_store):
    other_store.write_chapter("Other", "Act I", "other", "# theirs\n")
    other_store.git_commit("Other", "theirs")
    store.write_chapter(_SAFE_TITLE, "Act I", _SAFE_CHAPTER, "# mine\n")

    store.git_commit(_SAFE_TITLE, "mine")

    tracked = subprocess.run(
        ["git", "ls-tree", "-r", "--name-only", "HEAD"],
        cwd=str(store.account_dir()),
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    assert tracked.strip().splitlines() == ["Linchpin/Act I/Opening 1.md"]


def test_a_second_account_with_the_same_title_keeps_its_own_history(store, other_store):
    store.write_chapter(_SAFE_TITLE, "Act I", _SAFE_CHAPTER, "# mine\n")
    store.git_commit(_SAFE_TITLE, "mine")
    other_store.write_chapter(_SAFE_TITLE, "Act I", _SAFE_CHAPTER, "# theirs\n")

    other_store.git_commit(_SAFE_TITLE, "theirs")

    tracked = subprocess.run(
        ["git", "ls-tree", "-r", "--name-only", "HEAD"],
        cwd=str(other_store.account_dir()),
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    assert tracked.strip().splitlines() == ["Linchpin/Act I/Opening 1.md"]
    assert not store.document_exists("Other")


# ---------------------------------------------------------------------------
# DocumentStoreFactory
# ---------------------------------------------------------------------------


def test_factory_hands_out_one_accounts_store_at_a_time(tmp_path):
    factory = DocumentStoreFactory(base_dir=tmp_path)

    first = factory.for_account(_ACCOUNT)
    second = factory.for_account(_OTHER_ACCOUNT)

    assert first.account_dir() == tmp_path / _ACCOUNT
    assert second.account_dir() == tmp_path / _OTHER_ACCOUNT
    assert first.document_dir(_SAFE_TITLE) != second.document_dir(_SAFE_TITLE)


def test_factory_from_env_uses_dockb_chapters_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("DOCKB_CHAPTERS_DIR", str(tmp_path))

    store = DocumentStoreFactory.from_env().for_account(_ACCOUNT)

    assert store.document_dir(_SAFE_TITLE) == tmp_path / _ACCOUNT / _SAFE_TITLE


def test_factory_from_env_raises_when_unset(monkeypatch):
    monkeypatch.delenv("DOCKB_CHAPTERS_DIR", raising=False)
    with pytest.raises(ValueError, match="DOCKB_CHAPTERS_DIR"):
        DocumentStoreFactory.from_env()


def test_factory_refuses_an_empty_account_id(tmp_path):
    with pytest.raises(ValueError, match="account_id"):
        DocumentStoreFactory(base_dir=tmp_path).for_account("")


def test_adopt_document_copies_the_directory_and_commits_it(git_store, tmp_path):
    source = _other_document_tree(tmp_path, "# an imported chapter\n")

    git_store.adopt_document(_SAFE_TITLE, source)

    assert git_store.read_chapter(_SAFE_TITLE, "Act I", _SAFE_CHAPTER) == "# an imported chapter\n"
    assert source.is_dir()
    assert _porcelain(git_store) == ""
    assert _log_subjects(git_store) == [f"adopt: {_SAFE_TITLE}"]


def test_adopt_document_copies_every_file_in_the_tree(git_store, tmp_path):
    """Not just the chapter files: the document's own metadata travels with them."""
    source = _other_document_tree(tmp_path, "# one\n")
    (source / "Characters").mkdir(parents=True, exist_ok=True)
    (source / "Characters" / "Jael.md").write_text("# jael\n", encoding="utf-8")

    git_store.adopt_document(_SAFE_TITLE, source)

    assert git_store.chapter_exists(_SAFE_TITLE, "Characters", "Jael", category="Character")
    assert git_store.read_metadata(_SAFE_TITLE) == DocumentMetadata(title=_SAFE_TITLE, author="Test")


def test_adopt_document_refuses_to_write_over_an_existing_directory(git_store, tmp_path):
    """Two documents' files under one directory is a manuscript neither account wrote."""
    git_store.write_chapter(_SAFE_TITLE, "Act I", _SAFE_CHAPTER, "# the account's own\n")
    source = _other_document_tree(tmp_path, "# someone else's\n")

    with pytest.raises(SnapshotError, match="already exists"):
        git_store.adopt_document(_SAFE_TITLE, source)

    assert git_store.read_chapter(_SAFE_TITLE, "Act I", _SAFE_CHAPTER) == "# the account's own\n"


def test_adopt_document_missing_source_is_a_noop(git_store, tmp_path):
    """The graph holds the document's content regardless, so there is nothing to fail on."""
    git_store.adopt_document(_SAFE_TITLE, tmp_path / "never-existed")

    assert not git_store.document_exists(_SAFE_TITLE)


def test_adopt_document_rejects_an_unsafe_title(git_store, tmp_path):
    """The title is graph data, but it is still a title, and it still becomes a path."""
    source = _other_document_tree(tmp_path, "# body\n")

    with pytest.raises(ValueError, match="not a valid title"):
        git_store.adopt_document("../escape", source)


def test_adopt_document_commits_only_into_this_accounts_repository(git_store, other_store, tmp_path):
    """The whole point of a repository per account: a commit cannot span two of them."""
    source = _other_document_tree(tmp_path, "# adopted\n")

    git_store.adopt_document(_SAFE_TITLE, source)
    other_store.write_chapter("Theirs", "Act I", "Theirs One", "# theirs\n")
    other_store.git_commit("Theirs", "materialize: theirs")

    assert _log_subjects(git_store) == [f"adopt: {_SAFE_TITLE}"]
    assert _log_subjects(other_store) == ["materialize: theirs"]


def test_remove_legacy_document_deletes_the_flat_directory(tmp_path):
    factory = DocumentStoreFactory(base_dir=tmp_path)
    legacy = _other_document_tree(tmp_path, "# an imported chapter\n")
    (tmp_path / "Not This One").mkdir()

    factory.remove_legacy_document(_SAFE_TITLE)

    assert not legacy.exists()
    assert (tmp_path / "Not This One").is_dir()


def test_remove_legacy_document_missing_directory_is_a_noop(tmp_path):
    DocumentStoreFactory(base_dir=tmp_path).remove_legacy_document(_SAFE_TITLE)


def test_legacy_document_dir_is_the_title_under_the_base(tmp_path):
    assert DocumentStoreFactory(base_dir=tmp_path).legacy_document_dir(_SAFE_TITLE) == tmp_path / _SAFE_TITLE


def test_legacy_document_dir_rejects_an_unsafe_title(tmp_path):
    """A document's title is graph data; the path it becomes still has to stay inside the base."""
    with pytest.raises(ValueError, match="not a valid title"):
        DocumentStoreFactory(base_dir=tmp_path).legacy_document_dir("../escape")
