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


def test_cancel_on_done_job_is_noop():
    class ConcreteJob(Job):
        def run(self) -> None:
            self.status = JobStatus.DONE

    job = ConcreteJob()
    job.status = JobStatus.DONE
    job.cancel()
    assert job.status == JobStatus.DONE


def test_cancel_on_cancelled_job_is_noop():
    class ConcreteJob(Job):
        def run(self) -> None:
            pass

    job = ConcreteJob()
    job.cancel()
    assert job.status == JobStatus.CANCELLED
    job.cancel()
    assert job.status == JobStatus.CANCELLED


def test_cancel_on_queued_job_does_not_call_on_cancel():
    class TrackingJob(Job):
        on_cancel_called = False

        def run(self) -> None:
            pass

        def on_cancel(self) -> None:
            TrackingJob.on_cancel_called = True

    job = TrackingJob()
    job.cancel()
    assert job.status == JobStatus.CANCELLED
    assert not TrackingJob.on_cancel_called


def test_cancel_on_running_job_calls_on_cancel():
    class TrackingJob(Job):
        on_cancel_called = False

        def run(self) -> None:
            pass

        def on_cancel(self) -> None:
            TrackingJob.on_cancel_called = True

    job = TrackingJob()
    job.status = JobStatus.RUNNING
    job.cancel()
    assert job.status == JobStatus.CANCELLED
    assert TrackingJob.on_cancel_called


def test_cancel_on_failed_job_is_noop():
    class ConcreteJob(Job):
        def run(self) -> None:
            pass

    job = ConcreteJob()
    job.status = JobStatus.FAILED
    job.cancel()
    assert job.status == JobStatus.FAILED


def test_delete_job_run_with_no_model_does_nothing():
    job = DeleteJob()
    job.run()
    assert job.status == JobStatus.QUEUED


def test_delete_job_run_with_non_dirty_model_does_nothing():
    from dockb.models.sentence import Sentence

    job = DeleteJob()
    sentence = Sentence(text="Hello")
    sentence.dirty = False
    job.set(sentence)
    job.run()
    assert sentence.tokens == []
    assert job.model is None


def test_delete_job_run_clears_dirty_model():
    from dockb.models.sentence import Sentence
    from dockb.models.token import Token

    job = DeleteJob()
    sentence = Sentence(text="Hello")
    sentence.dirty = True
    sentence.tokens.append(Token(text="Hello"))
    job.set(sentence)
    job.run()
    assert len(sentence.tokens) == 0
    assert job.model is None


def test_reconstruct_job_run_with_no_model_does_nothing():
    job = ReconstructJob("model-1")
    job.run()
    assert job.status == JobStatus.QUEUED


def test_reconstruct_job_run_with_non_dirty_model_does_nothing(nlp):
    from dockb.models.sentence import Sentence
    from dockb.services.semantics.doc_cache import DocCache

    cache = DocCache(nlp)
    job = ReconstructJob("model-1")
    sentence = Sentence(text="Hello")
    sentence.dirty = False
    job.set(sentence, cache)
    job.run()
    assert len(sentence.tokens) == 0
    assert job.model is None


def test_reconstruct_job_on_cancel_with_tokenizer():
    from unittest.mock import MagicMock

    job = ReconstructJob("model-1")
    mock_tokenizer = MagicMock()
    job._tokenizer = mock_tokenizer
    job.on_cancel()
    mock_tokenizer.cancel.assert_called_once()


def test_reconstruct_job_on_cancel_without_tokenizer_does_nothing():
    job = ReconstructJob("model-1")
    job.on_cancel()
