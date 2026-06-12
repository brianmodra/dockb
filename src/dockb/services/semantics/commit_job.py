"""CommitJob — registers models with the UnitOfWork and commits when clean."""

from typing import Any

from dockb.infrastructure.neo4j.unit_of_work_factory import UnitOfWorkFactory
from dockb.models.base import DockbModel
from dockb.services.semantics.job import Job


class CommitJob(Job):
    """Job that registers previously-modified models with the current
    UnitOfWork and commits if none are dirty."""

    def __init__(self, factory: UnitOfWorkFactory) -> None:
        super().__init__()
        self._factory = factory
        self._models: list[tuple[DockbModel, dict[str, Any]]] = []

    def add(self, model: DockbModel, **parent_ids: str) -> None:
        """Register a model and its parent IDs for later dispatch."""
        self._models.append((model, parent_ids))

    def run(self) -> None:
        """Register all models with the UoW, then commit if none are dirty."""
        uow = self._factory.get_unit_of_work()
        for model, parent_ids in self._models:
            uow.register(model, **parent_ids)
        if any(model.dirty for model, _ in self._models):
            return
        uow.commit()
