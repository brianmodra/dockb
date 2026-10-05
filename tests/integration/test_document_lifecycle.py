"""Integration test: the whole document lifecycle against a live graph and git tree.

Wires real repositories, services, the document store and git together and
drives the full chain the API exposes: create a document -> open it ->
add chapters (first, middle, append) -> save a chapter -> absorb a hand edit
on open. Every step asserts the graph, the canonical files on disk and git
all agree.
"""

import subprocess

import pytest

from dockb.infrastructure.document_store import DocumentStoreFactory
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

ACCOUNT = "acct-lifecycle"

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
    """The document store's base directory, whose account subdirectory is a repository.

    The store creates the account's repository on first use, so the tests only need
    to supply a commit identity.
    """
    monkey_git_identity = pytest.MonkeyPatch()
    for name, value in (
        ("GIT_AUTHOR_NAME", "Test"),
        ("GIT_AUTHOR_EMAIL", "test@test.com"),
        ("GIT_COMMITTER_NAME", "Test"),
        ("GIT_COMMITTER_EMAIL", "test@test.com"),
    ):
        monkey_git_identity.setenv(name, value)
    yield tmp_path
    monkey_git_identity.undo()


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
    factory = DocumentStoreFactory(base_dir=git_repo)
    store = factory.for_account(ACCOUNT)
    doc_svc = DocumentService(
        uow_factory=uow_factory,
        document_repo=repos[Document],
        document_store_factory=factory,
        nlp=nlp,
    )
    ch_svc = ChapterService(
        uow_factory=uow_factory,
        chapter_repo=repos[Chapter],
        document_repo=repos[Document],
        document_store_factory=factory,
        nlp=nlp,
    )
    return doc_svc, ch_svc, store


def _git(store, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=str(store.account_dir()), capture_output=True, text=True, check=True).stdout


def _add_chapters(ch_svc, document_id: str) -> None:
    """Add chapters first, append, then middle (exercises middle reindex)."""
    ch_svc.create("c1", "First", document_id, after_chapter_id=None, owner=ACCOUNT)
    ch_svc.create("c3", "Third", document_id, after_chapter_id="c1", owner=ACCOUNT)
    ch_svc.create("c2", "Second", document_id, after_chapter_id="c1", owner=ACCOUNT)


def _assert_git_is_current(store, document_title: str, act: str, chapter_title: str) -> None:
    """Assert the file on disk matches git HEAD and the tree is clean."""
    act_dir = f"Act {act}" if act else "Act None"
    path = f"{document_title}/{act_dir}/{chapter_title}.md"
    committed = _git(store, "show", f"HEAD:{path}")
    assert committed == store.read_chapter(document_title, act, chapter_title)
    assert _git(store, "status", "--porcelain").strip() == ""
    assert _git(store, "log", "--oneline", "--", path).strip()


def _assert_empty_chapter_materialized(store):
    """Assert an empty chapter has a front-matter-only file committed to git."""
    for chapter_title in ("First", "Second", "Third"):
        assert store.chapter_exists("Lifecycle", "", chapter_title)
        content = store.read_chapter("Lifecycle", "", chapter_title)
        assert content is not None and content.startswith("---")
        _assert_git_is_current(store, "Lifecycle", "", chapter_title)


def test_document_lifecycle_chain(services, neo4j_session):
    """Create, open, order chapters, save, and reconcile a hand edit end to end."""
    doc_svc, ch_svc, store = services
    document_id = "d-lifecycle"
    try:
        doc = doc_svc.create(document_id, title="Lifecycle", author="Test", owner=ACCOUNT)
        assert doc.id == document_id
        assert store.read_metadata("Lifecycle") == DocumentMetadata(title="Lifecycle", author="Test")

        opened = doc_svc.open(document_id, ACCOUNT)
        assert opened is not None and opened.id == document_id

        _add_chapters(ch_svc, document_id)

        order = [row["id"] for row in ch_svc.list_by_document(document_id)]
        assert order == ["c1", "c2", "c3"]

        _assert_empty_chapter_materialized(store)

        result = ch_svc.save_document("c2", "First paragraph sentence.\n\nSecond paragraph.", ACCOUNT)
        assert result is not None
        assert result.summary.added == 2
        assert result.summary.changed == 0
        canonical = store.read_chapter("Lifecycle", "", "Second")
        assert canonical is not None
        assert "data-par-id" in canonical
        assert "id: c2" in canonical and "title: Second" in canonical

        hand_edit = canonical + "\n\nHand-written extra paragraph."
        store.chapter_file("Lifecycle", "", "Second").write_text(hand_edit, encoding="utf-8")
        reopened = ch_svc.open_document("c2", ACCOUNT)
        assert reopened is not None
        assert "Hand-written extra paragraph." in reopened

        loaded = ch_svc.get("c2")
        assert loaded is not None
        assert len(loaded.paragraphs) == 3
        assert "Hand-written extra paragraph." in loaded.get_text()
        _assert_git_is_current(store, "Lifecycle", "", "Second")
    finally:
        neo4j_session.run(_CLEANUP_CYPHER, {"id": document_id})


def _graph_has(neo4j_session, node_id: str) -> bool:
    return neo4j_session.run("MATCH (n {id: $id}) RETURN count(n) AS c", {"id": node_id}).single()["c"] > 0


def _graph_children(neo4j_session, node_id: str, depth: int) -> int:
    return neo4j_session.run(f"MATCH (n)-[:PART_OF*1..{depth}]->(x {{id: $id}}) RETURN count(n) AS c", {"id": node_id}).single()["c"]


def test_delete_cascades_graph_and_removes_store_files(services, neo4j_session):
    """Deleting a chapter/document removes the full graph subtree and the owned store files."""
    doc_svc, ch_svc, store = services
    document_id = "d-delete"
    try:
        doc = doc_svc.create(document_id, title="DeleteMe", author="Test", owner=ACCOUNT)
        assert doc.id == document_id
        _add_chapters(ch_svc, document_id)
        assert ch_svc.save_document("c2", "First paragraph sentence.\n\nSecond paragraph.", ACCOUNT) is not None
        assert _graph_children(neo4j_session, "c2", 3) >= 2

        # Chapter delete: graph subtree gone, own file git-rm'd, siblings intact.
        assert ch_svc.delete("c2", ACCOUNT) is True
        assert not _graph_has(neo4j_session, "c2")
        assert _graph_children(neo4j_session, "c2", 3) == 0
        assert not store.chapter_exists("DeleteMe", "", "Second")
        assert store.chapter_exists("DeleteMe", "", "First")
        assert store.document_exists("DeleteMe")
        assert any("remove: chapter Second" in line for line in _git(store, "log", "--oneline").splitlines())
        assert _git(store, "status", "--porcelain").strip() == ""

        # Same chapter title is free again: recreate is clean.
        ch_svc.create("c2b", "Second", document_id, after_chapter_id="c1", owner=ACCOUNT)
        assert _graph_has(neo4j_session, "c2b")
        assert store.chapter_exists("DeleteMe", "", "Second")
        assert _git(store, "status", "--porcelain").strip() == ""

        # Document delete: whole graph subtree and the whole store tree go.
        assert doc_svc.delete(document_id, ACCOUNT) is True
        assert not _graph_has(neo4j_session, document_id)
        assert _graph_children(neo4j_session, document_id, 2) == 0
        assert not store.document_exists("DeleteMe")
        assert any("remove: DeleteMe" in line for line in _git(store, "log", "--oneline").splitlines())
        assert _git(store, "status", "--porcelain").strip() == ""

        # Re-import path: the same id/title creates cleanly again.
        doc2 = doc_svc.create(document_id, title="DeleteMe", author="Test", owner=ACCOUNT)
        assert doc2.id == document_id
        assert store.document_exists("DeleteMe")
    finally:
        neo4j_session.run(_CLEANUP_CYPHER, {"id": document_id})


def test_rename_document_and_chapter_update_store_and_graph(services, neo4j_session):
    """Renaming a document or chapter moves the owned store files and keeps git clean."""
    doc_svc, ch_svc, store = services
    document_id = "d-rename"
    try:
        doc_svc.create(document_id, title="RenameMe", author="Test", owner=ACCOUNT)
        ch_svc.create("c1", "First", document_id, after_chapter_id=None, owner=ACCOUNT)
        assert store.document_exists("RenameMe")

        doc = doc_svc.update(document_id, title="Renamed", author="Author2", owner=ACCOUNT)
        assert doc is not None and doc.title == "Renamed"
        assert not store.document_exists("RenameMe")
        assert store.document_exists("Renamed")
        assert store.read_metadata("Renamed") == DocumentMetadata(title="Renamed", author="Author2")
        assert store.chapter_exists("Renamed", "", "First")
        assert _git(store, "status", "--porcelain").strip() == ""

        ch = ch_svc.update("c1", title="Second", owner=ACCOUNT)
        assert ch is not None and ch.title == "Second"
        assert not store.chapter_exists("Renamed", "", "First")
        assert store.chapter_exists("Renamed", "", "Second")
        assert "title: Second" in (store.read_chapter("Renamed", "", "Second") or "")
        assert _git(store, "status", "--porcelain").strip() == ""

        assert neo4j_session.run("MATCH (d:Document {id: $id}) RETURN d.title AS t", {"id": document_id}).single()["t"] == "Renamed"
        assert neo4j_session.run("MATCH (c:Chapter {id: 'c1'}) RETURN c.title AS t").single()["t"] == "Second"

        # Delete still removes the renamed tree end to end.
        assert doc_svc.delete(document_id, ACCOUNT) is True
        assert not store.document_exists("Renamed")
        assert not _graph_has(neo4j_session, document_id)
        assert _git(store, "status", "--porcelain").strip() == ""
    finally:
        neo4j_session.run(_CLEANUP_CYPHER, {"id": document_id})
