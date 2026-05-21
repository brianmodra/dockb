import gc
import logging
import threading
import time

import spacy
from cachetools import TTLCache
from spacy.language import Language
from spacy.tokens import Doc

try:
    _nlp = spacy.load("en_core_web_sm")
except OSError:
    _nlp = spacy.blank("en")


class DocCache:
    def __init__(self, max_size: int = 100, ttl: int = 60, sweep_time: int = 60, nlp: Language = None):
        """
        Construct a document cache which automatically evicts and does not allow the size to grow too large.
        :param max_size: don't let the number of docs in this cache exceed this
        :param ttl: documents older than this will be evicted automatically
        :param sweep_time: the time delay in between automatic sweeps, when the old documents are evicted.
        :param nlp: this is the language used for these documents
        """
        self.cache = TTLCache(maxsize=max_size, ttl=ttl, timer=time.time)
        if nlp == None:
            self.nlp = _nlp
        else:
            self.nlp = nlp
        self.sweep_time = sweep_time
        self.lock = threading.Lock()
        self.eviction_thread = None
        self.stop_signal = threading.Event()
        self.logger = logging.getLogger(__name__)
        self.logger.setLevel(logging.DEBUG)

    def has_doc(self, text: str) -> Doc:
        with self.lock:
            return text in self.cache

    def get_doc(self, text: str) -> Doc:
        with self.lock:
            if text in self.cache:
                doc = self.cache[text]
                # re-touch it so it gets the current time
                self.cache[text] = doc
                return doc

            # Otherwise, generate, cache, and return it
            doc = self.nlp(text)
            self.cache[text] = doc
            return doc

    def remove_doc(self, text: str) -> None:
        with self.lock:
            self.cache.pop(text, None)

    def _eviction_worker(self) -> None:
        """Periodically removes expired items from RAM in the background."""
        while not self.stop_signal.wait(self.sweep_time):
            self.evict()

    def evict(self) -> None:
        with self.lock:
            len_before = len(self.cache)
            self.cache.expire()
            if len(self.cache) < len_before:
                self.logger.debug(f"expired {len_before - self.len()}")
                gc.collect()

    def len(self) -> int:
        with self.lock:
            return len(self.cache)

    def start(self) -> None:
        self.eviction_thread = threading.Thread(target=self._eviction_worker, daemon=True)
        self.eviction_thread.start()

    def stop(self) -> None:
        if not self.eviction_thread:
            return
        self.stop_signal.set()
        self.eviction_thread.join()
