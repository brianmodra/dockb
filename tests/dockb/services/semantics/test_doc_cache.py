import spacy

from dockb.services.semantics.doc_cache import DocCache


def test_doc_cache_stores_and_evicts_as_expected(freezer):
    max_size: int = 2
    ttl: int = 60
    nlp = spacy.load("en_core_web_sm")
    sweep_time = 60
    cache = DocCache(nlp=nlp, max_size=max_size, ttl=ttl, sweep_time=sweep_time)
    doc1: spacy.tokens.Doc = cache.get_doc("Hello World!")
    doc2: spacy.tokens.Doc = cache.get_doc("Hello Mars!")
    doc3: spacy.tokens.Doc = cache.get_doc("Hello Moon!")
    # the two remaining objects in the cache should be the last two added only
    doc3_again: spacy.tokens.Doc = cache.get_doc("Hello Moon!")
    doc2_again: spacy.tokens.Doc = cache.get_doc("Hello Mars!")
    assert cache.len() == 2
    assert doc3 == doc3_again
    assert doc2 == doc2_again
    # doc1 should have been evicted from teh cache as it only stores 2 objects
    doc1_again: spacy.tokens.Doc = cache.get_doc("Hello World!")
    assert doc1 != doc1_again
    freezer.tick(30)
    # cause one eviction pass to execute
    # we need to do this manually because the eviction loop is in a thread,
    # and it does not use the freezer time
    cache.evict()
    assert cache.len() == 2
    # refresh doc1 so it will live another 60 seconds - this is important!
    cache.get_doc("Hello World!")
    freezer.tick(31)
    # cause another eviction pass to execute
    cache.evict()
    # "Hello World!" should still be there and the length should be one
    assert cache.len() == 1
    assert cache.has_doc("Hello World!")
    freezer.tick(31)
    # cause one more eviction pass to execute, then all should be gone
    cache.evict()
    assert cache.len() == 0


def test_doc_cache_remove_doc(nlp):
    cache = DocCache(nlp=nlp)
    cache.get_doc("Hello World!")
    assert cache.has_doc("Hello World!")

    cache.remove_doc("Hello World!")
    assert not cache.has_doc("Hello World!")


def test_doc_cache_remove_doc_missing_does_not_raise(nlp):
    cache = DocCache(nlp=nlp)
    cache.remove_doc("never existed")


def test_doc_cache_start_stop_lifecycle(nlp):
    cache = DocCache(nlp=nlp, sweep_time=60)
    cache.start()
    assert cache.eviction_thread is not None
    assert cache.eviction_thread.is_alive()

    cache.stop()
    assert not cache.eviction_thread.is_alive()


def test_doc_cache_stop_is_idempotent(nlp):
    cache = DocCache(nlp=nlp, sweep_time=60)
    cache.stop()
    cache.stop()


def test_doc_cache_join_with_no_thread_returns_immediately(nlp):
    cache = DocCache(nlp=nlp)
    cache.join()
