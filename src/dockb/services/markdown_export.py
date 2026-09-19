"""Reconstruct a chapter's markdown file from the knowledge graph."""

from __future__ import annotations

from pathlib import Path

from spacy.language import Language

from dockb.exceptions import ChapterMismatchError
from dockb.infrastructure.markdown import writer
from dockb.repositories.chapter_repository import ChapterRepository


def reconstruct_chapter_markdown(chapter_id: str, chapter_repo: ChapterRepository, nlp: Language) -> str:
    """Render the chapter with *chapter_id* from the graph to a complete chapter file.

    Raises ChapterMismatchError when the graph has no such chapter.
    """
    chapter = chapter_repo.load(chapter_id)
    if chapter is None:
        raise ChapterMismatchError(f"Chapter '{chapter_id}' was not found in the knowledge graph")
    return writer.render_chapter_markdown(chapter, nlp)


def reconstruct_chapter_file(chapter_id: str, chapter_repo: ChapterRepository, path: Path, nlp: Language) -> None:
    """Reconstruct the chapter with *chapter_id* from the graph and write it to *path*.

    Raises ChapterMismatchError when the graph has no such chapter.
    """
    chapter = chapter_repo.load(chapter_id)
    if chapter is None:
        raise ChapterMismatchError(f"Chapter '{chapter_id}' was not found in the knowledge graph")
    writer.write_chapter_markdown(chapter, path, nlp)
