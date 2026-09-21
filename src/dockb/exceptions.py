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


class DuplicateTitleError(Exception):
    """Raised when a document title already exists in the knowledge graph."""


class ChapterAfterNotFoundError(Exception):
    """Raised when after_chapter_id names a chapter that does not belong to the document."""
