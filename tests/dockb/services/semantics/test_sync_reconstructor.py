from dockb.models.chapter import Chapter
from dockb.models.document import Document
from dockb.models.paragraph import Paragraph
from dockb.models.sentence import Sentence
from dockb.services.semantics.doc_cache import DocCache
from dockb.services.semantics.sync_reconstructor import SyncReconstructor


def test_sync_reconstructor_runs_for_document(nlp):
    cache = DocCache(nlp)
    reconstructor = SyncReconstructor(cache, nlp)
    document = Document(text="Hello world!\f\fHello again. I'd say it is a good day.")
    document.dirty = True
    reconstructor.run(document)
    assert len(document.chapters) == 2
    assert not document.dirty


def test_sync_reconstructor_always_hydrates_document(nlp):
    cache = DocCache(nlp)
    reconstructor = SyncReconstructor(cache, nlp)
    document = Document(text="Hello world!")
    document.dirty = False
    reconstructor.run(document)
    assert len(document.chapters) == 1
    assert not document.dirty


def test_sync_reconstructor_runs_for_chapter(nlp):
    cache = DocCache(nlp)
    reconstructor = SyncReconstructor(cache, nlp)
    chapter = Chapter(text="Hello world!\n\nHello again. I'd say it is a good day.")
    chapter.dirty = True
    reconstructor.run(chapter)
    assert len(chapter.paragraphs) == 2
    assert not chapter.dirty


def test_sync_reconstructor_always_hydrates_chapter(nlp):
    cache = DocCache(nlp)
    reconstructor = SyncReconstructor(cache, nlp)
    chapter = Chapter(text="Hello world!")
    chapter.dirty = False
    reconstructor.run(chapter)
    assert len(chapter.paragraphs) == 1
    assert not chapter.dirty


def test_sync_reconstructor_runs_for_paragraph(nlp):
    cache = DocCache(nlp)
    reconstructor = SyncReconstructor(cache, nlp)
    paragraph = Paragraph(text="Hello world! This is another sentence.")
    paragraph.dirty = True
    reconstructor.run(paragraph)
    assert len(paragraph.sentences) == 2
    assert not paragraph.dirty


def test_sync_reconstructor_always_hydrates_paragraph(nlp):
    cache = DocCache(nlp)
    reconstructor = SyncReconstructor(cache, nlp)
    paragraph = Paragraph(text="Hello world!")
    paragraph.dirty = False
    reconstructor.run(paragraph)
    assert len(paragraph.sentences) == 1
    assert not paragraph.dirty


def test_sync_reconstructor_runs_for_sentence(nlp):
    cache = DocCache(nlp)
    reconstructor = SyncReconstructor(cache, nlp)
    sentence = Sentence(text="Hello world!")
    sentence.dirty = True
    reconstructor.run(sentence)
    assert len(sentence.tokens) > 0
    assert not sentence.dirty


def test_sync_reconstructor_always_tokenizes_sentence(nlp):
    cache = DocCache(nlp)
    reconstructor = SyncReconstructor(cache, nlp)
    sentence = Sentence(text="Hello world!")
    sentence.dirty = False
    reconstructor.run(sentence)
    assert len(sentence.tokens) > 0
    assert not sentence.dirty
