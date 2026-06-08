"""Cache for spaCy Doc objects with automatic TTL eviction."""

import gc
import logging
import threading
import time

from cachetools import TTLCache
from spacy.language import Language
from spacy.tokens import Doc


class DocCache:
    """
    Cache for spaCy Doc objects with automatic TTL eviction.

    Uses a background thread to periodically sweep and remove expired entries.
    """

    def __init__(
        self,
        nlp: Language,
        max_size: int = 100,
        ttl: int = 60,
        sweep_time: int = 60,
    ):
        """
        Construct a document cache with automatic eviction.

        Arguments:
            nlp: spaCy language pipeline for generating Doc objects.
            max_size: maximum number of docs allowed in the cache.
            ttl: seconds before a document expires.
            sweep_time: seconds between automatic eviction sweeps.
        """
        self.cache: TTLCache[str, Doc] = TTLCache(maxsize=max_size, ttl=ttl, timer=time.time)
        self.nlp = nlp
        self.sweep_time = sweep_time
        self.lock = threading.Lock()
        self.eviction_thread: threading.Thread | None = None
        self.stop_signal = threading.Event()
        self.logger = logging.getLogger(__name__)
        self.logger.setLevel(logging.DEBUG)

    def has_doc(self, text: str) -> bool:
        """Check if a doc for the given text is in the cache."""
        with self.lock:
            return text in self.cache

    def get_doc(self, text: str) -> Doc:
        """Get a cached doc or generate, cache, and return a new one."""
        with self.lock:
            doc: Doc
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
        """Remove a doc from the cache if present."""
        with self.lock:
            self.cache.pop(text, None)

    def _eviction_worker(self) -> None:
        """Periodically removes expired items from RAM in the background."""
        while not self.stop_signal.wait(self.sweep_time):
            self.evict()

    def evict(self) -> None:
        """Expire old entries and trigger garbage collection."""
        with self.lock:
            len_before = len(self.cache)
            self.cache.expire()
            if len(self.cache) < len_before:
                self.logger.debug("expired %d", len_before - self.len())
                gc.collect()

    def len(self) -> int:
        """Return the current number of items in the cache."""
        with self.lock:
            return len(self.cache)

    def start(self) -> None:
        """Start the background eviction thread."""
        self.eviction_thread = threading.Thread(target=self._eviction_worker, daemon=True)
        self.eviction_thread.start()

    def join(self) -> None:
        """Wait for any running eviction worker to finish."""
        if not self.eviction_thread:
            return
        self.eviction_thread.join()

    def stop(self) -> None:
        """Signal the eviction thread to stop and wait for it to finish."""
        if not self.eviction_thread:
            return
        self.stop_signal.set()
        self.eviction_thread.join()
