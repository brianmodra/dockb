"""Async sentence reconstruction via job queue."""

from dockb.models.base import DockbModel
from dockb.services.semantics.delete_job import DeleteJob
from dockb.services.semantics.doc_cache import DocCache
from dockb.services.semantics.job_queue import JobQueue
from dockb.services.semantics.reconstruct_job import ReconstructJob
from dockb.services.semantics.sentence_reconstructor import SentenceReconstructor


class AsyncSentenceReconstructor(SentenceReconstructor):  # pylint: disable=too-few-public-methods
    """Reconstructs sentences asynchronously using a job queue."""

    def __init__(self, doc_cache: DocCache, queue: JobQueue):
        super().__init__(doc_cache)
        self.queue = queue

    def run(self, model: DockbModel) -> None:
        """Queue a delete job followed by a reconstruct job for the model."""
        djob = DeleteJob()
        djob.set(model)
        self.queue.enqueue(djob)
        rjob = ReconstructJob(model.id)
        rjob.set(model, self.doc_cache)
        self.queue.enqueue(rjob)
