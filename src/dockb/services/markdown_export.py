"""Reconstruct a chapter's markdown file from the knowledge graph."""

from __future__ import annotations

from pathlib import Path

from spacy.language import Language

from dockb.exceptions import ChapterMismatchError
from dockb.infrastructure.document_store import DocumentStore
from dockb.infrastructure.markdown import writer
from dockb.repositories.chapter_repository import ChapterRepository
from dockb.repositories.document_repository import DocumentRepository


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


def reconstruct_chapter_to_store(
    chapter_id: str,
    chapter_repo: ChapterRepository,
    document_repo: DocumentRepository,
    store: DocumentStore,
    nlp: Language,
) -> Path:
    """Reconstruct *chapter_id* from the graph into the store's owned layout.

    The chapter is written to ``<base>/<document title>/<Act X>/<chapter
    title>.md`` — the same title/act-keyed tree the lifecycle services own —
    and git-committed through *store*, returning the written path. Raises
    ``ChapterMismatchError`` when the graph has no such chapter or the chapter
    has no owning document to place it under.
    """
    chapter = chapter_repo.load(chapter_id)
    if chapter is None:
        raise ChapterMismatchError(f"Chapter '{chapter_id}' was not found in the knowledge graph")
    document_id = chapter_repo.find_document_id(chapter_id)
    document = document_repo.load(document_id) if document_id is not None else None
    if document is None:
        raise ChapterMismatchError(f"Chapter '{chapter_id}' has no owning document")
    path = store.chapter_file(document.title, chapter.act, chapter.title)
    path.parent.mkdir(parents=True, exist_ok=True)
    writer.write_chapter_markdown(chapter, path, nlp)
    store.git_commit(document.title, f"reconstruct: {chapter_id[:8]}")
    return path
