from typing import TYPE_CHECKING

from dockb.models import DockbModel
from dockb.models.utils import DocCache
from dockb.services.semantics import DeleteJob, JobQueue, ReconstructJob

from .sentence_reconstructor import SentenceReconstructor

if TYPE_CHECKING:
    from dockb.models import Sentence


class AsyncSentenceReconstructor(SentenceReconstructor):
    def __init__(self, doc_cache: DocCache, queue: JobQueue):
        super().__init__(doc_cache)
        self.queue = queue

    def run(self, model: DockbModel):
        sentence: Sentence = model
        djob = DeleteJob()
        djob.set(sentence)
        self.queue.enqueue(djob)
        rjob = ReconstructJob(sentence.id)
        rjob.set(sentence, self.doc_cache)
        self.queue.enqueue(rjob)
