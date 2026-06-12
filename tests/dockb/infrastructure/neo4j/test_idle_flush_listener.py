"""Tests for IdleFlushListener."""

from unittest.mock import MagicMock

from dockb.infrastructure.neo4j.idle_flush_listener import IdleFlushListener
from dockb.infrastructure.neo4j.unit_of_work import UnitOfWork
from dockb.infrastructure.neo4j.unit_of_work_factory import UnitOfWorkFactory


class TestIdleFlushListener:
    def test_on_idle_flushes_pending_uow(self):
        factory = MagicMock(spec=UnitOfWorkFactory)
        uow = MagicMock(spec=UnitOfWork)
        factory.get_current_unit_of_work.return_value = uow
        listener = IdleFlushListener(factory)
        listener.on_idle()
        uow.flush_pending.assert_called_once()

    def test_on_idle_does_nothing_if_no_pending_uow(self):
        factory = MagicMock(spec=UnitOfWorkFactory)
        factory.get_current_unit_of_work.return_value = None
        listener = IdleFlushListener(factory)
        listener.on_idle()
        factory.get_current_unit_of_work.assert_called_once()
