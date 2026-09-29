"""Titles and acts that are safe to use as single filesystem path segments.

A document title, a chapter title, and a chapter's act all become path
segments under the document store's base directory, so each must be a single
segment that cannot climb out of the tree. The rule lives here, apart from
either the wire schema or the store, because it is a property of the value
rather than of the layer that happens to use it: the API rejects a hostile
title with a client error, and the store refuses to build a path from one, and
both must agree.
"""

from __future__ import annotations


def is_unsafe_segment(value: str) -> bool:
    """Return whether *value* cannot be used as a single path segment."""
    if not value:
        return True
    if value in {".", ".."}:
        return True
    if "/" in value or "\\" in value:
        return True
    return any(ord(char) < 32 or ord(char) == 127 for char in value)


def validate_segment(value: str) -> None:
    """Raise ``ValueError`` when *value* cannot be used as a single path segment."""
    if is_unsafe_segment(value):
        raise ValueError(f"{value!r} is not a valid title")
