"""Integration test: the whole document lifecycle against a live graph and git tree.

Wires real repositories, services, the document store and git together and
drives the full chain the API exposes: create a document -> open it ->
add chapters (first, middle, append) -> save a chapter -> absorb a hand edit
on open. Every step asserts the graph, the canonical files on disk and git
all agree.
"""

import subprocess

import pytest

from dockb.infrastructure.document_store import DocumentStore
from dockb.infrastructure.document_store.store import DocumentMetadata
from dockb.infrastructure.neo4j.unit_of_work_factory import UnitOfWorkFactory
from dockb.models.chapter import Chapter
from dockb.models.document import Document
from dockb.models.paragraph import Paragraph
from dockb.models.sentence import Sentence
from dockb.repositories.chapter_repository import ChapterRepository
from dockb.repositories.document_repository import DocumentRepository
from dockb.repositories.paragraph_repository import ParagraphRepository
from dockb.repositories.sentence_repository import SentenceRepository
from dockb.services.crud_services import ChapterService, DocumentService

pytestmark = pytest.mark.integration

_CLEANUP_CYPHER = """
MATCH (d:Document {id: $id})
OPTIONAL MATCH (c:Chapter)-[:PART_OF]->(d)
OPTIONAL MATCH (p:Paragraph)-[:PART_OF]->(c)
OPTIONAL MATCH (s:Sentence)-[:PART_OF]->(p)
OPTIONAL MATCH (t:Token)-[:PART_OF]->(s)
DETACH DELETE d, c, p, s, t
"""


@pytest.fixture()
def git_repo(tmp_path):
    """A temporary git repository rooted at the document store's base dir."""
    subprocess.run(["git", "init"], cwd=str(tmp_path), check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=str(tmp_path), check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=str(tmp_path), check=True, capture_output=True)
    return tmp_path


@pytest.fixture()
def services(neo4j_session, git_repo, nlp):
    """Repositories, unit-of-work factory and services wired to the live graph.

    The graph session is shared (session-scoped fixture); the document store is
    rooted in a fresh temp git repository.
    """
    repos = {
        Document: DocumentRepository(neo4j_session),
        Chapter: ChapterRepository(neo4j_session),
        Paragraph: ParagraphRepository(neo4j_session),
        Sentence: SentenceRepository(neo4j_session),
    }
    uow_factory = UnitOfWorkFactory(repos=repos, session_factory=None, reconstructor=None)
    store = DocumentStore(base_dir=git_repo)
    doc_svc = DocumentService(
        uow_factory=uow_factory,
        document_repo=repos[Document],
        document_store=store,
        nlp=nlp,
    )
    ch_svc = ChapterService(
        uow_factory=uow_factory,
        chapter_repo=repos[Chapter],
        document_repo=repos[Document],
        document_store=store,
        nlp=nlp,
    )
    return doc_svc, ch_svc, store


def _git(base, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=str(base), capture_output=True, text=True, check=True).stdout


def _add_chapters(ch_svc, document_id: str) -> None:
    """Add chapters first, append, then middle (exercises middle reindex)."""
    ch_svc.create("c1", "First", document_id, after_chapter_id=None)
    ch_svc.create("c3", "Third", document_id, after_chapter_id="c1")
    ch_svc.create("c2", "Second", document_id, after_chapter_id="c1")


def _assert_git_is_current(git_repo, store, document_id: str, chapter_id: str) -> None:
    """Assert the file on disk matches git HEAD and the tree is clean."""
    committed = _git(git_repo, "show", f"HEAD:{document_id}/chapter-{chapter_id}.md")
    assert committed == store.read_chapter(document_id, chapter_id)
    assert _git(git_repo, "status", "--porcelain").strip() == ""
    assert _git(git_repo, "log", "--oneline", "--", f"{document_id}/chapter-{chapter_id}.md").strip()


def _assert_empty_chapter_materialized(store, git_repo):
    """Assert an empty chapter has a front-matter-only file committed to git."""
    for chapter_id in ("c1", "c2", "c3"):
        assert store.chapter_exists("d-lifecycle", chapter_id)
        content = store.read_chapter("d-lifecycle", chapter_id)
        assert content is not None and content.startswith("---")
        _assert_git_is_current(git_repo, store, "d-lifecycle", chapter_id)


def test_document_lifecycle_chain(services, neo4j_session, git_repo):
    """Create, open, order chapters, save, and reconcile a hand edit end to end."""
    doc_svc, ch_svc, store = services
    document_id = "d-lifecycle"
    try:
        doc = doc_svc.create(document_id, title="Lifecycle", author="Test")
        assert doc.id == document_id
        assert store.read_metadata(document_id) == DocumentMetadata(title="Lifecycle", author="Test")

        opened = doc_svc.open(document_id)
        assert opened is not None and opened.id == document_id

        _add_chapters(ch_svc, document_id)

        order = [row["id"] for row in ch_svc.list_by_document(document_id)]
        assert order == ["c1", "c2", "c3"]

        _assert_empty_chapter_materialized(store, git_repo)

        result = ch_svc.save_document("c2", "First paragraph sentence.\n\nSecond paragraph.")
        assert result is not None
        assert result.summary.added == 2
        assert result.summary.changed == 0
        canonical = store.read_chapter(document_id, "c2")
        assert canonical is not None
        assert "data-par-id" in canonical
        assert "id: c2" in canonical and "title: Second" in canonical

        hand_edit = canonical + "\n\nHand-written extra paragraph."
        store.chapter_file(document_id, "c2").write_text(hand_edit, encoding="utf-8")
        reopened = ch_svc.open_document("c2")
        assert reopened is not None
        assert "Hand-written extra paragraph." in reopened

        loaded = ch_svc.get("c2")
        assert loaded is not None
        assert len(loaded.paragraphs) == 3
        assert "Hand-written extra paragraph." in loaded.get_text()
        _assert_git_is_current(git_repo, store, document_id, "c2")
    finally:
        neo4j_session.run(_CLEANUP_CYPHER, {"id": document_id})
