"""Shared YAML front-matter handling for chapter markdown files."""

from __future__ import annotations

from collections.abc import Mapping

import yaml

from dockb.exceptions import ChapterMismatchError


def parse(content: str) -> tuple[dict[str, object], str]:
    """Return ``(attrs, body)`` for *content*.

    A file with no opening ``---`` has no front matter: the attributes are empty
    and the body is the whole content. An opened-but-unclosed block, or a block
    that is not a YAML mapping, is malformed and raises ``ChapterMismatchError``.
    """
    if not content.startswith("---"):
        return {}, content
    lines = content.splitlines(keepends=True)
    closing = next((index for index in range(1, len(lines)) if lines[index].startswith("---")), None)
    if closing is None:
        raise ChapterMismatchError("Snapshot file is missing closing '---' for front matter")
    attrs = yaml.safe_load("".join(lines[1:closing])) or {}
    if not isinstance(attrs, dict):
        raise ChapterMismatchError("Front matter must be a mapping of key: value pairs")
    return dict(attrs), "".join(lines[closing + 1 :])


def render(attrs: Mapping[str, object]) -> str:
    """Render *attrs* as a complete ``---``-delimited front-matter block."""
    return "---\n" + _dump(dict(attrs)) + "---\n"


def merge(content: str, updates: Mapping[str, object]) -> str:
    """Return *content* with *updates* merged into its front matter, body kept.

    A file with no opening ``---`` gets a rendered block prepended; one with an
    existing block keeps its other attributes in place, only the keys in
    *updates* being added or overwritten.
    """
    if not content.startswith("---"):
        return render(updates) + content
    attrs, body = parse(content)
    attrs.update(updates)
    return render(attrs) + body


def _dump(attrs: dict[str, object]) -> str:
    return yaml.dump(attrs, default_flow_style=False, allow_unicode=True, sort_keys=False)
