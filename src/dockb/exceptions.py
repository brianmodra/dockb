"""Custom exceptions for the dockb package."""


class EditTextRangeError(Exception):
    """Raised when an edit text range is invalid."""

    def __init__(self, message: str, start: int, end: int):
        super().__init__(message)
        self.start = start
        self.end = end


class TokenInvalidError(Exception):
    """Raised when a token value is invalid."""


class SnapshotError(Exception):
    """Raised when a snapshot read or write operation fails."""


class ChapterMismatchError(Exception):
    """Raised when a markdown file's chapter identity disagrees with the chapter it is diffed against."""


class DocumentFormatError(ValueError):
    """Raised when a document directory is not laid out as the walker requires.

    A ``ValueError`` so a caller that already handles a bad value keeps
    working, but a named type so the import route can tell the caller's
    document being wrong from a bug of ours that happens to raise one.
    """


class DocumentNotFoundError(Exception):
    """No document with the given id exists, or *owner* does not own it.

    The two are the same error on purpose: a caller must not be able to tell a
    document belonging to someone else from one that was never created.
    """


class DocumentOwnershipError(Exception):
    """Raised when an operation is given no account to act for.

    A document is stored under the directory of the account that owns it, so an
    operation with a blank owner has nowhere to put the manuscript. Rejecting it up
    front also keeps a half-created document out of the graph, where it would belong
    to nobody and be reachable only through ``dockb users assign``.
    """


class ChapterNotFoundError(Exception):
    """No chapter with the given id exists, or *owner* does not own it.

    Same reasoning as :class:`DocumentNotFoundError`, one level down: a create writes
    through its parent, and a write whose parent belongs to somebody else must not be
    reported as a write that worked.
    """


class ParagraphNotFoundError(Exception):
    """No paragraph with the given id exists, or *owner* does not own it."""


class DuplicateTitleError(Exception):
    """Raised when a document title already exists in the knowledge graph."""


class ChapterAfterNotFoundError(Exception):
    """Raised when after_chapter_id names a chapter that does not belong to the document."""


class ChapterCategoryMismatchError(Exception):
    """Raised when a move would land a chapter outside its own category."""
