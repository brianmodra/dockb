"""Validating the paths and volume of a multipart document upload.

Every part of an upload arrives with a filename the caller chose, so the
filename is untrusted input that the server turns into a path. These rules are
kept apart from the route because they are the security boundary of the whole
feature: if one of them is wrong, an upload can read or overwrite files outside
the temporary directory it is written to.
"""

from __future__ import annotations

import re
from pathlib import Path, PurePosixPath

# A whole manuscript is text; these caps exist to stop one request exhausting
# memory or the disk, not to police legitimate documents.
MAX_TOTAL_BYTES = 64 * 1024 * 1024
MAX_FILE_COUNT = 2_000

_DRIVE_LETTER = re.compile(r"^[A-Za-z]:")


class UploadRejectedError(ValueError):
    """Raised when an upload cannot be accepted as a document directory."""


class UploadTooLargeError(UploadRejectedError):
    """An upload refused for its size rather than its shape.

    A subclass so the route can answer 413 for a cap and 422 for a malformed
    path, without re-deriving which of the two happened from the message.
    """


def validate_part_path(filename: str | None) -> PurePosixPath:
    """Return *filename* as a safe relative POSIX path, or raise.

    The name must be a relative path whose every segment is a real name, so
    that joining it onto a base directory cannot leave that directory. A
    backslash, a drive letter, a control character, or a ``.``/``..`` segment
    are all refused rather than normalised, because a client that means one of
    them is not describing the file the server should write.
    """
    if not filename:
        raise UploadRejectedError("a file part has no filename")
    if "\\" in filename:
        raise UploadRejectedError(f"filename must use '/' as its separator: {filename!r}")
    if _DRIVE_LETTER.match(filename):
        raise UploadRejectedError(f"filename must not name a drive: {filename!r}")
    if any(ord(char) < 32 or ord(char) == 127 for char in filename):
        raise UploadRejectedError(f"filename must not contain control characters: {filename!r}")
    if filename.startswith("/"):
        raise UploadRejectedError(f"filename must be relative: {filename!r}")

    # Checked on the raw name, not on the parsed path: PurePosixPath drops a
    # "." segment rather than refusing it, so a name carrying one has to be
    # caught here to be rejected as the docstring promises.
    for segment in filename.split("/"):
        if segment in {"", ".", ".."}:
            raise UploadRejectedError(f"filename must not contain a {segment!r} segment: {filename!r}")
    return PurePosixPath(filename)


def resolve_inside(base_dir: Path, relative: PurePosixPath) -> Path:
    """Return the path *relative* names inside *base_dir*, or raise.

    The path is checked twice: once on the segments, and once on the resolved
    result, so a path that is well-formed but still lands outside — through a
    symlink, or through a platform that resolves differently — is refused too.
    """
    root = base_dir.resolve()
    target = (base_dir / Path(*relative.parts)).resolve()
    if target != root and not target.is_relative_to(root):
        raise UploadRejectedError(f"filename escapes the upload directory: {str(relative)!r}")
    return target


def document_root(relative_paths: list[PurePosixPath]) -> str:
    """Return the single top-level directory name shared by *relative_paths*.

    An upload is one document directory, so every file has to arrive under the
    same document folder. That folder name is also the document's default
    title. A file with no directory at all is the mistake this refuses: it means
    the caller sent the document's files without the document.
    """
    if not relative_paths:
        raise UploadRejectedError("the upload contains no files")
    if any(len(path.parts) < 2 for path in relative_paths):
        raise UploadRejectedError("every file must be inside a document directory, so include that directory in the upload")
    roots = {path.parts[0] for path in relative_paths}
    if len(roots) > 1:
        raise UploadRejectedError(f"every file must belong to one document directory, but the upload spans {sorted(roots)}")
    return roots.pop()


class UploadBudget:  # pylint: disable=too-few-public-methods
    """The byte allowance for one upload, drawn down as its parts arrive.

    A cap is only meaningful if it covers the whole request, so the budget is
    shared by every part rather than measured per file. Charging before the
    bytes are written means a part that would cross the line is refused instead
    of being written and then rolled back.
    """

    def __init__(self, limit: int) -> None:
        self._limit = limit
        self._spent = 0

    def charge(self, count: int) -> None:
        """Account for *count* more bytes, or refuse the upload."""
        if self._spent + count > self._limit:
            raise UploadTooLargeError(f"upload too large: an upload is limited to {self._limit} bytes")
        self._spent += count
