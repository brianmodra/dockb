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

    def list_snapshots(self, chapter_id: str, *, limit: int = 20, offset: int = 0) -> list[dict[str, str]]:
        """Return snapshot history for *chapter_id* (most recent first)."""
        return self._reader.list_commits(chapter_id, limit=limit, offset=offset)

    def restore(self, chapter_id: str, commit_id: str) -> Chapter:
        """Read a snapshot at *commit_id*, persist it, and return the chapter."""

        chapter = self._reader.read_chapter(chapter_id, commit_id=commit_id)

        chapter.state = DataState.NEW
        uow = self._uow_factory.get_unit_of_work()
        uow.register(chapter, document_id="")
        uow.commit()

        return chapter
