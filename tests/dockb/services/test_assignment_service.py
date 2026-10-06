"""Tests for DocumentAssignmentService — giving a document to an account, tree and all.

The repository is a hand-written fake rather than a mock, because what these tests are
about is which of the service's questions is asked and what the service does with the
answer: a mock configured to return whatever the test expects would pass just as happily
against a service that never looked for the tree, or that stamped the owner before copying
the files. The fake records the order of what happened, so a service that copied nothing
has nothing to compare.

The store is real, over ``tmp_path``. The move is a filesystem operation with git
commits at both ends, and the question "did the files end up in the new account's tree,
committed" is not worth mocking.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from dockb.exceptions import DocumentFormatError, DocumentNotFoundError, DuplicateTitleError, SnapshotError
from dockb.infrastructure.document_store.factory import DocumentStoreFactory
from dockb.services.assignment_service import DocumentAssignmentService

_ALICE = "acct-alice"
_BOB = "acct-bob"
_TITLE = "Linchpin"


@pytest.fixture(autouse=True)
def git_identity(monkeypatch):
    """Give git a commit identity, as the store tests do.

    Environment variables rather than ``git config``, because each account directory is
    its own repository and is created by the code under test, so there is nothing to
    configure before it exists.
    """
    monkeypatch.setenv("GIT_AUTHOR_NAME", "Test")
    monkeypatch.setenv("GIT_AUTHOR_EMAIL", "test@test.com")
    monkeypatch.setenv("GIT_COMMITTER_NAME", "Test")
    monkeypatch.setenv("GIT_COMMITTER_EMAIL", "test@test.com")


class FakeDocumentRepo:
    """A document repository holding documents in memory, recording what was asked.

    Ownership is stored as ``None`` for a document with no owner — the absence the graph
    represents by the property being missing — so a test saying "unowned" is describing
    the same fact ``list_unowned`` reports.
    """

    def __init__(self, documents: list[dict[str, str | None]] | None = None) -> None:
        self.documents: dict[str, dict[str, str | None]] = {str(d["id"]): dict(d) for d in documents or []}
        self.events: list[str] = []

    def add(self, document_id: str, title: str, owner: str | None) -> None:
        self.documents[document_id] = {"id": document_id, "title": title, "owner": owner}

    def find_summary(self, document_id: str) -> dict[str, str | None] | None:
        self.events.append(f"find_summary({document_id})")
        found = self.documents.get(document_id)
        return dict(found) if found is not None else None

    def list_all(self, owner: str) -> list[dict[str, str | None]]:
        self.events.append(f"list_all({owner})")
        return [dict(d) for d in self.documents.values() if d["owner"] == owner]

    def list_unowned(self) -> list[dict[str, str]]:
        self.events.append("list_unowned()")
        return [{"id": str(d["id"]), "title": str(d["title"])} for d in self.documents.values() if not d["owner"]]

    def assign_owner(self, document_id: str, owner: str) -> bool:
        self.events.append(f"assign_owner({document_id},{owner})")
        if document_id not in self.documents:
            return False
        self.documents[document_id]["owner"] = owner
        return True


@pytest.fixture()
def repo() -> FakeDocumentRepo:
    return FakeDocumentRepo()


@pytest.fixture()
def factory(tmp_path) -> DocumentStoreFactory:
    return DocumentStoreFactory(base_dir=tmp_path)


@pytest.fixture()
def service(repo, factory) -> DocumentAssignmentService:
    return DocumentAssignmentService(repo, factory)


def _write_tree(base: Path, account: str | None, title: str, body: str = "first line\n") -> Path:
    """Write a one-chapter document tree, flat when *account* is None."""
    root = base / title if account is None else base / account / title
    chapter = root / "Act I" / "One.md"
    chapter.parent.mkdir(parents=True, exist_ok=True)
    chapter.write_text(body, encoding="utf-8")
    return chapter


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.is_file() else ""


def _git_log(base: Path, account: str) -> list[str]:
    """Return the account repository's commit subjects, oldest first."""
    result = subprocess.run(
        ["git", "log", "--reverse", "--format=%s"],
        cwd=str(base / account),
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.splitlines()


class TestAssigningAnUnownedDocument:
    def test_it_gives_the_document_to_the_account(self, service, repo):
        repo.add("d-1", _TITLE, None)

        assignment = service.assign("d-1", _ALICE)

        assert repo.documents["d-1"]["owner"] == _ALICE
        assert assignment.document_id == "d-1"
        assert assignment.title == _TITLE
        assert assignment.account_id == _ALICE
        assert assignment.already_owned is False

    def test_it_moves_the_flat_legacy_tree_into_the_accounts_directory(self, service, repo, factory, tmp_path):
        """A manuscript imported before trees were per-account sits at ``<base>/<title>``.

        Its files may be the only copy of work the graph never saw, so they are copied
        into the new owner's tree rather than left behind for a tree that nothing reads.
        """
        repo.add("d-1", _TITLE, None)
        legacy = _write_tree(tmp_path, None, _TITLE)
        before = _read(legacy)

        assignment = service.assign("d-1", _ALICE)

        adopted = factory.for_account(_ALICE).chapter_file(_TITLE, "Act I", "One")
        assert _read(adopted) == before
        assert not legacy.parent.parent.exists()
        assert assignment.tree_moved is True

    def test_it_moves_the_tree_out_of_the_previous_accounts_directory(self, service, repo, factory, tmp_path):
        """A transfer out of a live account — or a soft-deleted one — moves that tree."""
        repo.add("d-1", _TITLE, _BOB)
        original = _write_tree(tmp_path, _BOB, _TITLE)

        assignment = service.assign("d-1", _ALICE)

        adopted = factory.for_account(_ALICE).chapter_file(_TITLE, "Act I", "One")
        assert adopted.is_file()
        assert not original.exists()
        assert assignment.tree_moved is True

    def test_the_previous_accounts_repository_records_the_removal(self, service, repo, factory, tmp_path):
        """Otherwise its next commit sweeps in a deletion nobody made.

        The old account keeps its own repository, so an uncommitted ``git rm`` would sit
        in the working tree until something else committed, attributing the removal to
        whatever change came next. The document is committed in bob's repository first,
        because that is the state a document written through the editor is in — there is
        nothing to record a removal from otherwise.
        """
        repo.add("d-1", _TITLE, _BOB)
        _write_tree(tmp_path, _BOB, _TITLE)
        factory.for_account(_BOB).git_commit(_TITLE, "save: chapter one")

        service.assign("d-1", _ALICE)

        assert _git_log(tmp_path, _BOB) == ["save: chapter one", "remove: Linchpin"]

    def test_an_untracked_tree_leaves_nothing_to_commit_behind(self, service, repo, tmp_path):
        """A directory the old repository never committed produces no removal commit.

        Not a case worth failing over: there is no history claiming the files were
        there, so recording their absence would be a commit about nothing.
        """
        repo.add("d-1", _TITLE, _BOB)
        _write_tree(tmp_path, _BOB, _TITLE)

        service.assign("d-1", _ALICE)

        assert not (tmp_path / _BOB / _TITLE).exists()

    def test_it_commits_the_moved_tree_in_the_new_accounts_repository(self, service, repo, tmp_path):
        repo.add("d-1", _TITLE, None)
        _write_tree(tmp_path, None, _TITLE)

        service.assign("d-1", _ALICE)

        assert _git_log(tmp_path, _ALICE) == ["adopt: Linchpin"]

    def test_the_moved_tree_carries_no_history_from_the_old_repository(self, service, repo, tmp_path):
        """History is not carried across repositories, and this is what that looks like.

        The destination sees one commit, not the source account's. Stitching the history
        across would mean ``format-patch`` per commit for a tree that only ever held one
        account's work.
        """
        repo.add("d-1", _TITLE, None)
        _write_tree(tmp_path, None, _TITLE)
        service.assign("d-1", _ALICE)
        _write_tree(tmp_path, _ALICE, "Something Else")
        factory = DocumentStoreFactory(base_dir=tmp_path)
        factory.for_account(_ALICE).git_commit("Something Else", "save: something else")

        service.assign("d-1", _BOB)

        assert _git_log(tmp_path, _ALICE) == ["adopt: Linchpin", "save: something else", "remove: Linchpin"]
        assert _git_log(tmp_path, _BOB) == ["adopt: Linchpin"]

    def test_it_prefers_the_owners_directory_over_the_flat_one(self, service, repo, tmp_path):
        """Two directories, one title: the account's own is the one that was written.

        The flat path is the older layout, so it is the fallback. When both exist the
        account's copy is the manuscript and the flat one is left alone — deleting a
        directory this command cannot vouch for is not part of moving a document.
        """
        repo.add("d-1", _TITLE, _BOB)
        owned = _write_tree(tmp_path, _BOB, _TITLE, body="the account's copy\n")
        legacy = _write_tree(tmp_path, None, _TITLE, body="the older copy\n")

        service.assign("d-1", _ALICE)

        adopted = tmp_path / _ALICE / _TITLE / "Act I" / "One.md"
        assert _read(adopted) == "the account's copy\n"
        assert _read(owned) == ""
        assert legacy.is_file()

    def test_it_removes_the_flat_tree_of_a_document_that_has_an_owner(self, service, repo, tmp_path):
        """Which layout the tree was in decides how it is deleted, not who owns the document.

        A document can have an owner and a tree that predates per-account directories —
        the account directory was never written, or was lost. Its only files are then in
        the flat layout, and a removal that went looking in the account's repository would
        delete nothing and leave them there for whichever document next claims the title.
        """
        repo.add("d-1", _TITLE, _BOB)
        legacy = _write_tree(tmp_path, None, _TITLE, body="written before accounts owned it\n")

        service.assign("d-1", _ALICE)

        assert not legacy.parent.parent.exists()
        assert _read(tmp_path / _ALICE / _TITLE / "Act I" / "One.md") == "written before accounts owned it\n"
        assert _git_log(tmp_path, _ALICE) == ["adopt: Linchpin"]
        assert not (tmp_path / _BOB).exists()

    def test_it_assigns_a_document_that_has_no_tree_on_disk(self, service, repo, factory):
        """The graph is the source of truth, so a missing directory is not a failure.

        The editor materializes the tree from the graph when the document is opened, so
        refusing here would strand a document that is perfectly readable.
        """
        repo.add("d-1", _TITLE, None)

        assignment = service.assign("d-1", _ALICE)

        assert repo.documents["d-1"]["owner"] == _ALICE
        assert assignment.tree_moved is False
        assert not factory.for_account(_ALICE).document_exists(_TITLE)

    def test_it_leaves_the_other_documents_in_the_old_tree_alone(self, service, repo, tmp_path):
        """The account's repository is not emptied; one document left it."""
        repo.add("d-1", _TITLE, _BOB)
        repo.add("d-2", "Other", _BOB)
        _write_tree(tmp_path, _BOB, _TITLE)
        kept = _write_tree(tmp_path, _BOB, "Other")

        service.assign("d-1", _ALICE)

        assert kept.is_file()


class TestOrderOfOperations:  # pylint: disable=too-few-public-methods
    def test_it_copies_before_it_stamps_and_stamps_before_it_removes(self, service, repo, tmp_path):
        """Each interruption leaves something recoverable, which is why the order is this.

        Crash before the stamp: the document is still unowned and the copy is in place —
        the next run refuses with the title the account already holds, naming the
        directory to look at. Crash after the stamp but before the removal: a stale
        directory nothing reads, since no read of the old tree happens for a document it
        no longer owns. The reverse order would leave the document owned by the new
        account with its markdown still in the old tree, which the editor would
        silently paper over by re-materializing from the graph.
        """
        repo.add("d-1", _TITLE, _BOB)
        source = _write_tree(tmp_path, _BOB, _TITLE)
        destination = tmp_path / _ALICE / _TITLE / "Act I" / "One.md"
        seen: list[tuple[bool, bool]] = []

        def record(document_id: str, owner: str) -> bool:
            seen.append((destination.is_file(), source.is_file()))
            return FakeDocumentRepo.assign_owner(repo, document_id, owner)

        repo.assign_owner = record  # type: ignore[method-assign]

        service.assign("d-1", _ALICE)

        assert seen == [(True, True)]


class TestRefusals:
    def test_it_refuses_a_document_the_graph_does_not_have(self, service, repo):
        repo.add("d-1", _TITLE, None)

        with pytest.raises(DocumentNotFoundError):
            service.assign("d-missing", _ALICE)

        assert "assign_owner" not in " ".join(repo.events)

    def test_it_refuses_a_title_that_cannot_be_stored(self, service, repo):
        """A document whose title cannot name a directory is refused, not crashed on.

        The tree is moved by title, so an empty title or one holding a path separator has
        nowhere to go. A build that did not validate titles could write one, and the
        operator should get a refusal naming the document rather than a ValueError from
        path validation three calls deep.
        """
        repo.add("d-1", "", None)

        with pytest.raises(DocumentFormatError) as refusal:
            service.assign("d-1", _ALICE)

        assert "d-1" in str(refusal.value)
        assert repo.documents["d-1"]["owner"] is None

    def test_it_refuses_a_title_the_account_already_holds(self, service, repo, factory, tmp_path):
        """The graph's ``(owner, title_key)`` constraint would refuse this too.

        Two documents' files under one directory is a manuscript neither account wrote,
        and the titles would differ only in case — which the graph sees as one title and
        a filesystem may see as one name.
        """
        repo.add("d-1", _TITLE, None)
        repo.add("d-2", _TITLE, _ALICE)
        _write_tree(tmp_path, None, _TITLE)

        with pytest.raises(DuplicateTitleError) as refusal:
            service.assign("d-1", _ALICE)

        assert "d-2" in str(refusal.value)
        assert repo.documents["d-1"]["owner"] is None
        assert not factory.for_account(_ALICE).document_exists(_TITLE)

    def test_a_refusal_leaves_the_documents_only_copy_of_its_files_in_place(self, service, repo, tmp_path):
        """Nothing is written — including no removal from where the files are.

        A refusal that removed the source before discovering the clash would leave a
        document whose graph says one thing and whose only markdown says another, with the
        markdown gone.
        """
        repo.add("d-1", _TITLE, None)
        repo.add("d-2", _TITLE, _ALICE)
        only_copy = _write_tree(tmp_path, None, _TITLE, body="never imported anywhere\n")

        with pytest.raises(DuplicateTitleError):
            service.assign("d-1", _ALICE)

        assert _read(only_copy) == "never imported anywhere\n"

    def test_the_refusal_catches_a_title_differing_only_in_case(self, service, repo):
        repo.add("d-1", "linchpin", None)
        repo.add("d-2", "Linchpin", _ALICE)

        with pytest.raises(DuplicateTitleError):
            service.assign("d-1", _ALICE)

    def test_it_refuses_when_the_accounts_directory_already_holds_the_title(self, service, repo, tmp_path):
        """The store's own refusal, for a caller that skipped the graph check.

        The service compares titles in the graph, which is where a clash is visible; the
        store refuses the write regardless, because a store that merged two directories
        would be the one place a manuscript nobody wrote could be created.
        """
        repo.add("d-1", _TITLE, _BOB)
        _write_tree(tmp_path, _BOB, _TITLE)
        _write_tree(tmp_path, _ALICE, _TITLE, body="a different document's files\n")

        with pytest.raises(SnapshotError):
            service.assign("d-1", _ALICE)


class TestAssigningToTheAccountThatAlreadyHoldsIt:
    def test_it_writes_nothing_and_says_so(self, service, repo, tmp_path):
        repo.add("d-1", _TITLE, _ALICE)
        existing = _write_tree(tmp_path, _ALICE, _TITLE)

        assignment = service.assign("d-1", _ALICE)

        assert assignment.already_owned is True
        assert assignment.tree_moved is False
        assert existing.is_file()
        assert repo.events == ["find_summary(d-1)"]

    def test_the_id_is_not_mistaken_for_a_clash_with_itself(self, service, repo):
        """The account holding the document is not a second document holding its title."""
        repo.add("d-1", _TITLE, _ALICE)

        assert service.assign("d-1", _ALICE).already_owned is True
