"""Moving a manuscript from the account that has it to the account that should.

One document belongs to nobody before accounts owned manuscripts, and one belongs to an
account that can no longer sign in. Both are unreachable over HTTP — an unowned document
is in nobody's library, and a soft-deleted account cannot authenticate — while the
manuscript itself is perfectly readable in the graph. This service is the one way back,
and it is called from the command line only: an ownership transfer has no counterpart in
the editor, by design, so the editor gains no transfer surface.

Two things move together, in this order:

1. The markdown tree, copied into the destination account's directory and committed
   there. A pre-ownership tree sits at ``<base>/<title>`` with no account segment, one
   that has an owner sits at ``<base>/<that account id>/<title>``, and a document can
   have neither — the graph is the source of truth and the editor materializes a tree on
   first open, so a document with no directory is still assigned.
2. The ``owner`` property in the graph.

The tree moves first because it is the recoverable half: a crash before the stamp leaves
the document unowned with a copy in place, which the next run reports as a title the
account already holds — naming the directory the operator has to look at. A crash after
the stamp but before the old tree is gone leaves a stale directory that nothing reads,
because no read of the old account's tree happens for a document it no longer owns.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from dockb.exceptions import DocumentFormatError, DocumentNotFoundError, DuplicateTitleError
from dockb.infrastructure.document_store.factory import DocumentStoreFactory
from dockb.repositories.document_repository import DocumentRepository
from dockb.titles import validate_segment


@dataclass(frozen=True)
class _TreeSource:
    """A document's markdown directory, and whose repository it is in.

    The two layouts are not interchangeable, so which one a tree was found in has to
    travel with it: removing it afterwards means a different thing in each, and a
    document that has an owner but whose tree is still in the flat pre-ownership layout
    must have that directory removed, not an absent one from its account's repository.
    """

    path: Path
    owner: str | None  # None for the flat pre-ownership layout.


@dataclass(frozen=True)
class Assignment:
    """What one assignment did, for the caller to report.

    ``tree_moved`` says whether there was a directory to move, which is the difference
    between "assigned, and its markdown came with it" and "assigned; its markdown was
    already in the graph". ``already_owned`` marks the one case where nothing was written
    at all: the document was already the destination's.
    """

    document_id: str
    title: str
    account_id: str
    tree_moved: bool
    already_owned: bool


class DocumentAssignmentService:  # pylint: disable=too-few-public-methods
    """Gives documents to accounts, moving each one's markdown tree with it.

    One method on purpose. The batch form is the command's, not the service's: it owns
    how many refusals a run collects and what the exit code becomes, which is a question
    about a command line rather than about a document.
    """

    def __init__(self, document_repo: DocumentRepository, store_factory: DocumentStoreFactory) -> None:
        self._document_repo = document_repo
        self._store_factory = store_factory

    def assign(self, document_id: str, account_id: str) -> Assignment:
        """Give the document with *document_id* to *account_id* and move its tree.

        Refuses, having written nothing, when the document does not exist
        (:class:`DocumentNotFoundError`), when its title cannot be used as a directory
        name (:class:`DocumentFormatError`), or when *account_id* already holds a document
        of the same title (:class:`DuplicateTitleError`, whose message names both ids).
        Assigning to the account that already holds the document is not a refusal and
        writes nothing: it is reported as ``already_owned``.

        The account is not checked for being deleted or blocked here. Whether an account
        is a valid destination is a question about accounts, answered by the account store
        the command line already holds, and this service knows nothing about logins.
        """
        summary = self._document_repo.find_summary(document_id)
        if summary is None:
            raise DocumentNotFoundError(document_id)
        title = str(summary["title"] or "")
        self._refuse_unusable_title(title, document_id)
        current_owner = summary["owner"]
        if current_owner == account_id:
            return Assignment(
                document_id=document_id,
                title=title,
                account_id=account_id,
                tree_moved=False,
                already_owned=True,
            )
        self._refuse_title_clash(title, document_id, account_id)

        source = self._locate_tree(title, current_owner)
        destination = self._store_factory.for_account(account_id)
        if source is not None:
            destination.adopt_document(title, source.path)

        if not self._document_repo.assign_owner(document_id, account_id):
            raise DocumentNotFoundError(document_id)

        if source is not None:
            self._remove_tree(title, source.owner)

        return Assignment(
            document_id=document_id,
            title=title,
            account_id=account_id,
            tree_moved=source is not None,
            already_owned=False,
        )

    def _refuse_unusable_title(self, title: str, document_id: str) -> None:
        """Refuse a document whose title cannot name a directory.

        The tree is moved by title, so an empty title or one holding a path separator
        cannot be copied anywhere. A document written by a build that did not validate
        titles can hold one, and the operator is better served by a refusal naming the
        document than by a traceback from path validation three calls deep — the command
        catches :class:`DocumentFormatError` and prints one ``error:`` line.
        """
        try:
            validate_segment(title)
        except ValueError as exc:
            raise DocumentFormatError(f"document {document_id} has a title that cannot be stored: {exc}") from exc

    def _refuse_title_clash(self, title: str, document_id: str, account_id: str) -> None:
        """Refuse when *account_id* already holds a different document titled *title*.

        The comparison is case-insensitive because that is how the graph's
        ``(owner, title_key)`` constraint sees it, and because two documents differing
        only in case cannot both live in one account's tree under two spellings of a name
        a filesystem may treat as equal.
        """
        for row in self._document_repo.list_all(account_id):
            if str(row.get("title") or "").lower() == title.lower() and row.get("id") != document_id:
                raise DuplicateTitleError(
                    f"{title!r} is already held by this account as {row['id']}; "
                    "rename or reassign that document before assigning this one"
                )

    def _locate_tree(self, title: str, current_owner: str | None) -> _TreeSource | None:
        """Return where the document's markdown directory is, or None when it has none.

        The account's own directory first, then the flat pre-ownership path. An account
        directory is checked first because a document that has an owner and a tree there
        has a tree that was written under that owner; the flat path is the older layout,
        so it is the fallback rather than the alternative — and when both exist the flat
        one is left where it is, since nothing reads a directory whose document now
        belongs elsewhere.
        """
        if current_owner is not None:
            owned = self._store_factory.for_account(current_owner).document_dir(title)
            if owned.is_dir():
                return _TreeSource(path=owned, owner=current_owner)
        legacy = self._store_factory.legacy_document_dir(title)
        return _TreeSource(path=legacy, owner=None) if legacy.is_dir() else None

    def _remove_tree(self, title: str, source_owner: str | None) -> None:
        """Delete the directory the document's tree was moved from.

        An account's directory goes through the store, which removes the files with ``git
        rm`` and commits the removal, so that repository does not keep working-tree
        deletions staged for its next commit. The flat pre-ownership directory is simply
        deleted: the repository that used to hold it is the one per-account repositories
        replaced, and nothing reads it.

        Which of the two is decided by where the tree was *found*, not by who owns the
        document now: a document with an owner whose tree is still in the flat layout has
        a flat directory to delete and no account directory to delete it from.
        """
        if source_owner is not None:
            self._store_factory.for_account(source_owner).remove_document(title)
            return
        self._store_factory.remove_legacy_document(title)
