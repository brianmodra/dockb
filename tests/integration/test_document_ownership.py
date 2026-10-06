"""Integration test: two accounts' documents stay apart in the graph and on disk.

The mocked repository tests assert that ``owner`` appears in each query's ``MATCH``;
this drives the real graph, so it proves the property those assertions stand for — a
document belonging to one account is invisible to another, and the markdown tree of two
accounts holding the same title does not collide.
"""

import pytest

from dockb.exceptions import DocumentOwnershipError
from dockb.infrastructure.document_store import DocumentStoreFactory
from dockb.infrastructure.neo4j.unit_of_work_factory import UnitOfWorkFactory
from dockb.models.chapter import Chapter
from dockb.models.document import Document
from dockb.models.paragraph import Paragraph
from dockb.models.sentence import Sentence
from dockb.repositories.chapter_repository import ChapterRepository
from dockb.repositories.document_repository import DocumentRepository
from dockb.repositories.paragraph_repository import ParagraphRepository
from dockb.repositories.sentence_repository import SentenceRepository
from dockb.services.crud_services import DocumentService

pytestmark = pytest.mark.integration

_ALICE = "acct-alice"
_BOB = "acct-bob"

_CLEANUP_CYPHER = """
MATCH (d:Document)
WHERE d.id IN $ids
OPTIONAL MATCH (c:Chapter)-[:PART_OF]->(d)
OPTIONAL MATCH (p:Paragraph)-[:PART_OF]->(c)
OPTIONAL MATCH (s:Sentence)-[:PART_OF]->(p)
OPTIONAL MATCH (t:Token)-[:PART_OF]->(s)
DETACH DELETE d, c, p, s, t
"""


@pytest.fixture()
def services(neo4j_session, tmp_path):
    """A DocumentService over the live graph and a per-account store factory."""
    repos = {
        Document: DocumentRepository(neo4j_session),
        Chapter: ChapterRepository(neo4j_session),
        Paragraph: ParagraphRepository(neo4j_session),
        Sentence: SentenceRepository(neo4j_session),
    }
    factory = DocumentStoreFactory(base_dir=tmp_path)
    service = DocumentService(
        uow_factory=UnitOfWorkFactory(repos=repos, session_factory=None, reconstructor=None),
        document_repo=repos[Document],
        document_store_factory=factory,
    )
    return service, repos[Document], factory, tmp_path


def test_two_accounts_do_not_see_each_others_documents(services, neo4j_session):
    service, repo, _factory, _base = services
    try:
        alice_doc = service.create("d-alice", title="Opening", author="Alice", owner=_ALICE)
        bob_doc = service.create("d-bob", title="Opening", author="Bob", owner=_BOB)

        assert alice_doc.id == "d-alice"
        assert bob_doc.id == "d-bob"

        alice_ids = [row["id"] for row in repo.list_all(_ALICE)]
        bob_ids = [row["id"] for row in repo.list_all(_BOB)]
        assert alice_ids == ["d-alice"]
        assert bob_ids == ["d-bob"]
    finally:
        neo4j_session.run(_CLEANUP_CYPHER, {"ids": ["d-alice", "d-bob"]})


def test_a_document_reads_as_absent_to_another_account(services, neo4j_session):
    """Another account's id must be indistinguishable from one that never existed.

    Both are ``None``; there is no separate "forbidden" answer to tell a caller that
    the document exists but belongs to someone else.
    """
    service, repo, _factory, _base = services
    try:
        service.create("d-alice", title="Opening", author="Alice", owner=_ALICE)

        assert repo.load("d-alice", _ALICE) is not None
        assert repo.load_shell("d-alice", _ALICE) is not None
        assert repo.load("d-alice", _BOB) is None
        assert repo.load_shell("d-alice", _BOB) is None
        assert repo.load("d-never-existed", _BOB) is None
    finally:
        neo4j_session.run(_CLEANUP_CYPHER, {"ids": ["d-alice"]})


def test_a_document_with_no_owner_is_invisible_to_everyone(services, neo4j_session):
    """A document from before ownership existed belongs to nobody, not to the first caller.

    It is reachable only through ``dockb users assign``, which is the whole point of
    keeping the backfill command rather than letting a login claim it.
    """
    _service, repo, _factory, _base = services
    try:
        legacy = Document(id="d-legacy", title="Legacy", author="Nobody")
        neo4j_session.run(
            "MERGE (d:Document {id: $id}) SET d.title = $title, d.author = $author, d.title_key = $title_key",
            {"id": "d-legacy", "title": "Legacy", "author": "Nobody", "title_key": "legacy"},
        )
        assert legacy.owner == ""

        assert repo.find_summary("d-legacy")["owner"] is None
        assert repo.find_summary("d-legacy")["title"] == "Legacy"
        assert repo.list_all(_ALICE) == []
        assert repo.load_shell("d-legacy", _ALICE) is None
    finally:
        neo4j_session.run(_CLEANUP_CYPHER, {"ids": ["d-legacy"]})


def test_creating_a_document_with_no_account_is_refused(services, neo4j_session):
    """An unowned document cannot be created through the service at all.

    Documents that predate ownership exist only as legacy data in the graph, with no
    ``owner`` property and no tree of their own; ``dockb users assign`` gives them one.
    A create with a blank owner is refused before anything is written, so a document
    can never end up in the graph belonging to nobody as the result of a request.
    """
    service, repo, _factory, base = services
    try:
        with pytest.raises(DocumentOwnershipError):
            service.create("d-orphan", title="Orphan", author="Nobody", owner="")

        assert repo.find_summary("d-orphan") is None
        assert repo.list_all(_ALICE) == []
        assert not list(base.iterdir())
    finally:
        neo4j_session.run(_CLEANUP_CYPHER, {"ids": ["d-orphan"]})


def test_two_legacy_documents_may_share_a_title(services, neo4j_session):
    """Legacy documents are outside the per-owner constraint, so backfill cannot deadlock.

    ``document_title_key_per_owner`` only indexes documents that carry an ``owner``,
    so a legacy database can hold two same-titled documents that no account can reach
    -- and it must remain possible to hand them to two different accounts. If
    unowned documents were indexed as one bucket they would collide on migration and
    the recovery command would have nothing it could succeed on.
    """
    service, repo, _factory, _base = services
    try:
        for suffix in ("one", "two"):
            service.create(f"d-legacy-{suffix}", title="Legacy", author="Nobody", owner=_ALICE)
            neo4j_session.run(
                "MATCH (d:Document {id: $id}) REMOVE d.owner",
                {"id": f"d-legacy-{suffix}"},
            )

        # Subset, not equality: the database is shared across the integration suite, so an
        # unowned document another test has not cleaned up yet is not this test's failure.
        assert {"d-legacy-one", "d-legacy-two"} <= {row["id"] for row in repo.list_unowned()}
        assert repo.load_shell("d-legacy-one", _ALICE) is None
        assert repo.load_shell("d-legacy-two", _ALICE) is None
    finally:
        neo4j_session.run(_CLEANUP_CYPHER, {"ids": ["d-legacy-one", "d-legacy-two"]})


def test_the_same_title_coexists_for_two_accounts_on_disk(services, neo4j_session):
    service, _repo, factory, base = services
    try:
        service.create("d-alice", title="Opening", author="Alice", owner=_ALICE)
        service.create("d-bob", title="Opening", author="Bob", owner=_BOB)

        alice = factory.for_account(_ALICE)
        bob = factory.for_account(_BOB)
        assert alice.document_dir("Opening") != bob.document_dir("Opening")
        assert alice.document_dir("Opening").is_dir()
        assert bob.document_dir("Opening").is_dir()
        assert alice.document_dir("Opening") == base / _ALICE / "Opening"
        assert bob.document_dir("Opening") == base / _BOB / "Opening"
    finally:
        neo4j_session.run(_CLEANUP_CYPHER, {"ids": ["d-alice", "d-bob"]})


def test_an_accounts_git_repository_is_provisioned_on_its_first_commit(services, neo4j_session):
    """The account directory becomes a repository only when it is first used as one.

    The base directory holds one directory per account, and creating a document in it
    is not by itself a versioning event, so nothing creates a repository nobody has
    committed to.
    """
    service, _repo, factory, _base = services
    try:
        service.create("d-alice", title="Opening", author="Alice", owner=_ALICE)

        alice = factory.for_account(_ALICE)
        assert not (alice.account_dir() / ".git").exists()

        alice.git_commit("Opening", "first")
        assert (alice.account_dir() / ".git").is_dir()
    finally:
        neo4j_session.run(_CLEANUP_CYPHER, {"ids": ["d-alice"]})


def test_opening_a_document_materializes_only_its_owners_tree(services, neo4j_session):
    """A rejected open must leave the wrong account's filesystem untouched.

    The titles differ deliberately: if both accounts held the same title, the other
    account's directory could not tell "my document" from "their document" by name.
    """
    service, _repo, factory, _base = services
    try:
        service.create("d-alice", title="Opening", author="Alice", owner=_ALICE)
        service.create("d-bob", title="Closing", author="Bob", owner=_BOB)

        alice_tree = factory.for_account(_ALICE)
        bob_tree = factory.for_account(_BOB)

        assert service.open("d-bob", owner=_ALICE) is None
        assert alice_tree.document_dir("Opening").is_dir()
        assert not alice_tree.document_dir("Closing").exists()

        assert service.open("d-bob", owner=_BOB) is not None
        assert bob_tree.document_dir("Closing").is_dir()
    finally:
        neo4j_session.run(_CLEANUP_CYPHER, {"ids": ["d-alice", "d-bob"]})
