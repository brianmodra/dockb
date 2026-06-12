"""Tests for CommitJob."""

from unittest.mock import MagicMock

from dockb.infrastructure.neo4j.unit_of_work import UnitOfWork
from dockb.infrastructure.neo4j.unit_of_work_factory import UnitOfWorkFactory
from dockb.models.base import DataState
from dockb.models.document import Document
from dockb.services.semantics.commit_job import CommitJob
from dockb.services.semantics.job import Job, JobStatus


class TestCommitJob:
    def test_is_a_job(self):
        factory = MagicMock(spec=UnitOfWorkFactory)
        job = CommitJob(factory)
        assert isinstance(job, Job)
        assert isinstance(job.id, str)
        assert job.status == JobStatus.QUEUED

    def test_registers_models_with_uow(self):
        factory = MagicMock(spec=UnitOfWorkFactory)
        uow = MagicMock(spec=UnitOfWork)
        factory.get_unit_of_work.return_value = uow
        job = CommitJob(factory)
        model = Document()
        model.state = DataState.NEW
        model.dirty = False
        job.add(model, document_id="d1")
        job.run()
        factory.get_unit_of_work.assert_called_once()
        uow.register.assert_called_once_with(model, document_id="d1")
        uow.commit.assert_called_once()

    def test_registers_multiple_models(self):
        factory = MagicMock(spec=UnitOfWorkFactory)
        uow = MagicMock(spec=UnitOfWork)
        factory.get_unit_of_work.return_value = uow
        job = CommitJob(factory)
        model1 = Document()
        model1.state = DataState.NEW
        model1.dirty = False
        model2 = Document()
        model2.state = DataState.CHANGED
        model2.dirty = False
        job.add(model1)
        job.add(model2, document_id="d2")
        job.run()
        assert uow.register.call_count == 2
        uow.commit.assert_called_once()

    def test_defers_if_any_model_is_dirty(self):
        factory = MagicMock(spec=UnitOfWorkFactory)
        uow = MagicMock(spec=UnitOfWork)
        factory.get_unit_of_work.return_value = uow
        job = CommitJob(factory)
        model = Document()
        model.state = DataState.NEW
        model.dirty = True
        job.add(model)
        job.run()
        uow.register.assert_called_once()
        uow.commit.assert_not_called()

    def test_commits_when_no_models_dirty(self):
        factory = MagicMock(spec=UnitOfWorkFactory)
        uow = MagicMock(spec=UnitOfWork)
        factory.get_unit_of_work.return_value = uow
        job = CommitJob(factory)
        model = Document()
        model.state = DataState.SYNC
        model.dirty = False
        job.add(model)
        job.run()
        uow.commit.assert_called_once()

    def test_add_accepts_variable_parent_ids(self):
        factory = MagicMock(spec=UnitOfWorkFactory)
        uow = MagicMock(spec=UnitOfWork)
        factory.get_unit_of_work.return_value = uow
        job = CommitJob(factory)
        model = Document()
        model.state = DataState.NEW
        model.dirty = False
        job.add(model, document_id="d1", chapter_id="c1")
        job.run()
        uow.register.assert_called_once_with(model, document_id="d1", chapter_id="c1")

    def test_add_can_be_called_multiple_times(self):
        factory = MagicMock(spec=UnitOfWorkFactory)
        uow = MagicMock(spec=UnitOfWork)
        factory.get_unit_of_work.return_value = uow
        job = CommitJob(factory)
        model1 = Document()
        model1.state = DataState.NEW
        model1.dirty = False
        model2 = Document()
        model2.state = DataState.CHANGED
        model2.dirty = False
        job.add(model1, document_id="d1")
        job.add(model2, document_id="d2")
        job.run()
        assert uow.register.call_count == 2

    def test_has_timeout_set(self):
        factory = MagicMock(spec=UnitOfWorkFactory)
        job = CommitJob(factory)
        assert job.timeout == 5.0
