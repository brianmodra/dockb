from dockb.models.sentence import Sentence
from dockb.services.semantics.doc_cache import DocCache
from dockb.services.semantics.sync_sentence_reconstructor import SyncSentenceReconstructor


def test_sync_sentence_reconstructor_runs(nlp):
    cache = DocCache(nlp)
    reconstructor = SyncSentenceReconstructor(cache)
    sentence = Sentence(text="Hello world!")
    sentence.dirty = True
    reconstructor.run(sentence)
    assert len(sentence.tokens) > 0
    assert not sentence.dirty


def test_sync_sentence_reconstructor_always_tokenizes(nlp):
    cache = DocCache(nlp)
    reconstructor = SyncSentenceReconstructor(cache)
    sentence = Sentence(text="Hello world!")
    sentence.dirty = False
    reconstructor.run(sentence)
    assert len(sentence.tokens) > 0
    assert not sentence.dirty


def test_sync_sentence_reconstructor_skips_model_without_tokens(nlp):
    from dockb.models.chapter import Chapter

    cache = DocCache(nlp)
    reconstructor = SyncSentenceReconstructor(cache)
    chapter = Chapter(text="Hello world!")
    chapter.dirty = True
    reconstructor.run(chapter)
