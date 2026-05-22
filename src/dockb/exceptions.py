"""Custom exceptions for the dockb package."""


class EditTextRangeError(Exception):
    """Raised when an edit text range is invalid."""

    def __init__(self, message: str, start: int, end: int):
        super().__init__(message)
        self.start = start
        self.end = end


class TokenInvalidError(Exception):
    """Raised when a token value is invalid."""
