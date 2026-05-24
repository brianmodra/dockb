import threading

from dockb.services.semantics.delete_job import DeleteJob
from dockb.services.semantics.job import Job, JobStatus
from dockb.services.semantics.reconstruct_job import ReconstructJob


class SimpleJob(Job):
    ready = threading.Event()

    def run(self) -> None:
        self.ready.wait()

    def set(self) -> None:
        self.ready.set()


class ConcreteJob(Job):
    def run(self) -> None:
        pass


def test_job_runs():
    job = SimpleJob()
    job.set()
    job.run()  # runs without raising


def test_job_cancel():
    job = ConcreteJob()
    job.cancel()
    assert job.status == JobStatus.CANCELLED


def test_each_job_has_unique_id():
    job1 = ConcreteJob()
    job2 = ConcreteJob()
    assert job1.id != job2.id
    assert isinstance(job1.id, str)


def test_delete_job_has_unique_id():
    class ConcreteDelete(DeleteJob):
        def run(self) -> None:
            pass

    job1 = ConcreteDelete()
    job2 = ConcreteDelete()
    assert job1.id != job2.id
    assert isinstance(job1.id, str)


def test_reconstruct_job_has_unique_id():
    class ConcreteReconstruct(ReconstructJob):
        def run(self) -> None:
            pass

    job1 = ConcreteReconstruct(model_id="model-1")
    job2 = ConcreteReconstruct(model_id="model-2")
    assert job1.id != job2.id
    assert isinstance(job1.id, str)
    assert job1.model_id == "model-1"
    assert job2.model_id == "model-2"
