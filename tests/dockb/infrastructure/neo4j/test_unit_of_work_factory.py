"""Tests for UnitOfWorkFactory."""

from typing import Any
from unittest.mock import MagicMock

import pytest

from dockb.infrastructure.neo4j.session_factory import SessionFactory
from dockb.infrastructure.neo4j.unit_of_work_factory import UnitOfWorkFactory
from dockb.models.base import DockbModel
from dockb.models.document import Document


@pytest.fixture
def factory() -> UnitOfWorkFactory:
    session_factory = MagicMock(spec=SessionFactory)
    reconstructor = MagicMock()
    repos: dict[type[DockbModel], Any] = {Document: MagicMock()}
    return UnitOfWorkFactory(
        repos=repos,
        session_factory=session_factory,
        reconstructor=reconstructor,
    )


class TestUnitOfWorkFactoryGetUnitOfWork:
    def test_returns_same_instance_before_commit(self, factory: UnitOfWorkFactory) -> None:
        uow1 = factory.get_unit_of_work()
        uow2 = factory.get_unit_of_work()
        assert uow1 is uow2

    def test_returns_new_instance_after_commit(self, factory: UnitOfWorkFactory) -> None:
        uow1 = factory.get_unit_of_work()
        model = Document()
        model.state = model.state  # keep default
        uow1.commit(factory._repos)
        uow2 = factory.get_unit_of_work()
        assert uow2 is not uow1

    def test_implicitly_creates_new_after_commit_on_next_call(self, factory: UnitOfWorkFactory) -> None:
        uow1 = factory.get_unit_of_work()
        uow1.commit(factory._repos)
        assert factory.get_unit_of_work() is not uow1


class TestUnitOfWorkFactoryGetCurrentUnitOfWork:
    def test_returns_none_before_first_call(self, factory: UnitOfWorkFactory) -> None:
        assert factory.get_current_unit_of_work() is None

    def test_returns_current_uow(self, factory: UnitOfWorkFactory) -> None:
        uow = factory.get_unit_of_work()
        assert factory.get_current_unit_of_work() is uow

    def test_returns_none_after_commit(self, factory: UnitOfWorkFactory) -> None:
        uow = factory.get_unit_of_work()
        uow.commit(factory._repos)
        assert factory.get_current_unit_of_work() is None


class TestUnitOfWorkFactoryConstructedUoW:
    def test_uow_has_reconstructor(self, factory: UnitOfWorkFactory) -> None:
        uow = factory.get_unit_of_work()
        assert uow._reconstructor is factory._reconstructor

    def test_uow_has_repos(self, factory: UnitOfWorkFactory) -> None:
        uow = factory.get_unit_of_work()
        assert uow._repos is factory._repos

    def test_uow_has_on_commit_callback(self, factory: UnitOfWorkFactory) -> None:
        uow = factory.get_unit_of_work()
        assert uow._on_commit is not None

    def test_on_commit_callback_creates_new_uow(self, factory: UnitOfWorkFactory) -> None:
        uow1 = factory.get_unit_of_work()
        uow1.commit(factory._repos)
        uow2 = factory.get_unit_of_work()
        assert uow2 is not uow1
