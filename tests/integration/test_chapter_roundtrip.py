"""Integration test: persist a chapter hierarchy to Neo4j and read it back identically."""

import pytest

from dockb.infrastructure.neo4j.unit_of_work import UnitOfWork
from dockb.models.base import DataState
from dockb.models.chapter import Chapter
from dockb.models.document import Document
from dockb.models.paragraph import Paragraph
from dockb.models.sentence import Sentence
from dockb.repositories.chapter_repository import ChapterRepository
from dockb.repositories.document_repository import DocumentRepository
from dockb.repositories.paragraph_repository import ParagraphRepository
from dockb.repositories.sentence_repository import SentenceRepository
from dockb.services.semantics.chapter_hydrator import ChapterHydrator
from dockb.services.semantics.doc_cache import DocCache
from dockb.services.semantics.paragraph_hydrator import ParagraphHydrator
from dockb.services.semantics.sentence_tokenizer import SentenceTokenizer

pytestmark = pytest.mark.integration

CHAPTER_TEXT = (
    "First paragraph first sentence. First paragraph second sentence.\n\n"
    "Second paragraph first sentence. Second paragraph second sentence. "
    "Second paragraph third sentence."
)

_CLEANUP_CYPHER = """
MATCH (d:Document {id: $id})
OPTIONAL MATCH (c:Chapter)-[:PART_OF]->(d)
OPTIONAL MATCH (p:Paragraph)-[:PART_OF]->(c)
OPTIONAL MATCH (s:Sentence)-[:PART_OF]->(p)
OPTIONAL MATCH (t:Token)-[:PART_OF]->(s)
DETACH DELETE d, c, p, s, t
"""

_TOKENS_FIELDS = [
    "text",
    "type",
    "trailing_ws",
    "pos",
    "lemma",
    "is_digit",
    "like_num",
    "is_alpha",
    "is_stop",
]


def _build_and_hydrate(nlp) -> Document:
    """Create a Document with one chapter, hydrate paragraphs/sentences, and tokenize."""
    doc = Document()
    chapter = Chapter(text=CHAPTER_TEXT)
    doc.append_child(chapter)

    ChapterHydrator().hydrate(chapter)

    para_hydrator = ParagraphHydrator(nlp)
    doc_cache = DocCache(nlp)
    tokenizer = SentenceTokenizer()

    for para in chapter.paragraphs:
        para_hydrator.hydrate(para)
        for sent in para.sentences:
            sent.tokens[:] = tokenizer.tokenize(sent.text, doc_cache)

    doc.state = DataState.NEW
    chapter.state = DataState.NEW
    for para in chapter.paragraphs:
        para.state = DataState.NEW
        for sent in para.sentences:
            sent.state = DataState.NEW

    return doc


def _save(neo4j_session, doc: Document) -> None:
    """Persist a Document with full hierarchy through UnitOfWork."""
    repos = {
        Document: DocumentRepository(neo4j_session),
        Chapter: ChapterRepository(neo4j_session),
        Paragraph: ParagraphRepository(neo4j_session),
        Sentence: SentenceRepository(neo4j_session),
    }
    uow = UnitOfWork(repos=repos)
    uow.register(doc)
    uow.register(doc.chapters[0], document_id=doc.id)
    for para in doc.chapters[0].paragraphs:
        uow.register(para, chapter_id=doc.chapters[0].id)
        for sent in para.sentences:
            uow.register(sent, paragraph_id=para.id)
    uow.commit()


def _assert_structures_match(loaded: Document, original: Document) -> None:
    """Compare two document trees — structure, token properties, and text."""
    orig_chapter = original.chapters[0]
    loaded_chapter = loaded.chapters[0]

    assert len(loaded_chapter.paragraphs) == len(orig_chapter.paragraphs)

    for p_idx, (orig_p, loaded_p) in enumerate(zip(orig_chapter.paragraphs, loaded_chapter.paragraphs, strict=True)):
        assert len(loaded_p.sentences) == len(orig_p.sentences), f"paragraph {p_idx} sentence count"
        for s_idx, (orig_s, loaded_s) in enumerate(zip(orig_p.sentences, loaded_p.sentences, strict=True)):
            assert len(loaded_s.tokens) == len(orig_s.tokens), f"paragraph {p_idx} sentence {s_idx} token count"
            for t_idx, (orig_t, loaded_t) in enumerate(zip(orig_s.tokens, loaded_s.tokens, strict=True)):
                for field in _TOKENS_FIELDS:
                    assert getattr(orig_t, field) == getattr(loaded_t, field), (
                        f"mismatch at para[{p_idx}] sent[{s_idx}] tok[{t_idx}] "
                        f"field={field!r} expected={getattr(orig_t, field)!r} "
                        f"got={getattr(loaded_t, field)!r}"
                    )

    assert loaded_chapter.get_text() == orig_chapter.get_text()
    for orig_p, loaded_p in zip(orig_chapter.paragraphs, loaded_chapter.paragraphs, strict=True):
        assert loaded_p.get_text() == orig_p.get_text()
        for orig_s, loaded_s in zip(orig_p.sentences, loaded_p.sentences, strict=True):
            assert loaded_s.get_text() == orig_s.get_text()


def test_chapter_roundtrip(neo4j_session, nlp):
    """Build a chapter, save to Neo4j, read back, compare, and clean up."""
    doc = _build_and_hydrate(nlp)

    _save(neo4j_session, doc)

    doc_repo = DocumentRepository(neo4j_session)
    loaded_doc = doc_repo.load(doc.id)
    assert loaded_doc is not None
    _assert_structures_match(loaded_doc, doc)

    neo4j_session.run(_CLEANUP_CYPHER, {"id": doc.id})
