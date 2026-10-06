"""History service — snapshot listing and chapter restoration."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from dockb.models.base import DataState

if TYPE_CHECKING:
    from dockb.infrastructure.history.snapshot_reader import SnapshotReader
    from dockb.infrastructure.neo4j.unit_of_work_factory import UnitOfWorkFactory
    from dockb.models.chapter import Chapter
    from dockb.repositories.chapter_repository import ChapterRepository

logger = logging.getLogger(__name__)


class HistoryService:
    """List snapshots and restore chapters from git history."""

    def __init__(
        self,
        reader: SnapshotReader,
        chapter_repo: ChapterRepository,
        uow_factory: UnitOfWorkFactory,
    ) -> None:
        self._reader = reader
        self._chapter_repo = chapter_repo
        self._uow_factory = uow_factory

    def list_snapshots(self, chapter_id: str, *, owner: str, limit: int = 20, offset: int = 0) -> list[dict[str, str]]:
        """Return snapshot history for *chapter_id* (most recent first).

        The snapshot repository is shared by every account and keyed by chapter id alone,
        which is not an account boundary, so the chapter is claimed against *owner*
        first. A chapter of another account's document lists the same as a chapter with
        no history: nothing.
        """
        if self._chapter_repo.find_document_id(chapter_id, owner) is None:
            return []
        return self._reader.list_commits(chapter_id, limit=limit, offset=offset)

    def restore(self, chapter_id: str, commit_id: str, *, owner: str) -> Chapter | None:
        """Read a snapshot at *commit_id*, persist it, and return the chapter.

        Returns None when *owner* does not own the chapter, which the route reports as
        404 — the same answer as a chapter that does not exist.

        The chapter is written back under the document that owns it. Without that it
        would be re-persisted as an orphan, detached from every document, and invisible
        to the account that just asked for it.
        """
        document_id = self._chapter_repo.find_document_id(chapter_id, owner)
        if document_id is None:
            return None

        chapter = self._reader.read_chapter(chapter_id, commit_id=commit_id)

        chapter.state = DataState.NEW
        uow = self._uow_factory.get_unit_of_work()
        uow.register(chapter, document_id=document_id, owner=owner)
        uow.commit()

        return chapter
