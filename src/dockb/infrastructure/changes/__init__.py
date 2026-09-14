"""Paragraph-level change detection between a hydrated chapter and a markdown file."""

from dockb.infrastructure.changes.detect_changes import (
    ChangedParagraph,
    ChapterDiff,
    NewParagraph,
    detect_changes,
)

__all__ = [
    "ChapterDiff",
    "ChangedParagraph",
    "NewParagraph",
    "detect_changes",
]
