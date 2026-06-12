"""Listener that flushes pending UnitOfWork on idle signal."""

from dockb.infrastructure.neo4j.unit_of_work_factory import UnitOfWorkFactory


class IdleFlushListener:  # pylint: disable=too-few-public-methods
    """JobQueue idle listener that flushes any pending UnitOfWork."""

    def __init__(self, factory: UnitOfWorkFactory) -> None:
        self._factory = factory

    def on_idle(self) -> None:
        """Flush the pending UnitOfWork if one exists."""
        uow = self._factory.get_current_unit_of_work()
        if uow is not None:
            uow.flush_pending()
