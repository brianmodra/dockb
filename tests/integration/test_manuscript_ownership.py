"""Integration test: one account's chapters, paragraphs and sentences stay its own.

The mocked repository tests assert that ``owner`` appears in each query's ``MATCH``;
this drives the real graph, so it proves the property those assertions stand for — once a
chapter exists under an account's document, every other account reads it as absent, cannot
write into it, and cannot mistake it for its own.
"""

import pytest

from dockb.exceptions import ChapterNotFoundError, DocumentNotFoundError, ParagraphNotFoundError
from dockb.infrastructure.neo4j.unit_of_work_factory import UnitOfWorkFactory
from dockb.models.chapter import Chapter
from dockb.models.document import Document
from dockb.models.paragraph import Paragraph
from dockb.models.sentence import Sentence
from dockb.repositories.chapter_repository import ChapterRepository
from dockb.repositories.document_repository import DocumentRepository
from dockb.repositories.paragraph_repository import ParagraphRepository
from dockb.repositories.sentence_repository import SentenceRepository
from dockb.services.crud_services import (
    ChapterService,
    DocumentService,
    ParagraphService,
    SentenceService,
)

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
def services(neo4j_session):
    """Services wired to the live graph with no store, so writes are graph-only."""
    repos = {
        Document: DocumentRepository(neo4j_session),
        Chapter: ChapterRepository(neo4j_session),
        Paragraph: ParagraphRepository(neo4j_session),
        Sentence: SentenceRepository(neo4j_session),
    }
    uow_factory = UnitOfWorkFactory(repos=repos, session_factory=None, reconstructor=None)
    return {
        "document": DocumentService(uow_factory=uow_factory, document_repo=repos[Document]),
        "chapter": ChapterService(uow_factory=uow_factory, chapter_repo=repos[Chapter], document_repo=repos[Document]),
        "paragraph": ParagraphService(uow_factory=uow_factory, paragraph_repo=repos[Paragraph]),
        "sentence": SentenceService(uow_factory=uow_factory, sentence_repo=repos[Sentence]),
        "repos": repos,
    }


def _alice_manuscript(services):
    """Build a document with one chapter, one paragraph and one sentence under *alice*."""
    services["document"].create("d-alice", title="Opening", author="Alice", owner=_ALICE)
    services["chapter"].create("c-alice", "Intro", document_id="d-alice", owner=_ALICE)
    services["paragraph"].create("p-alice", content=[Sentence(id="s-alice")], chapter_id="c-alice", owner=_ALICE)
    return services


def _assert_nothing_was_created(neo4j_session, document_id: str) -> None:
    """Assert the document holds only the ids *alice* put there.

    A rejected write must leave no trace: a refused create that still wrote a
    paragraph, sentence or chapter would hand the next caller someone else's content.
    """
    rows = neo4j_session.run(
        """
        MATCH (d:Document {id: $id})
        OPTIONAL MATCH (c:Chapter)-[:PART_OF]->(d)
        OPTIONAL MATCH (p:Paragraph)-[:PART_OF]->(c)
        OPTIONAL MATCH (s:Sentence)-[:PART_OF]->(p)
        RETURN collect(DISTINCT c.id) AS chapters,
               collect(DISTINCT p.id) AS paragraphs,
               collect(DISTINCT s.id) AS sentences
        """,
        {"id": document_id},
    ).single()
    assert sorted(rows["chapters"]) == ["c-alice"]
    assert sorted(rows["paragraphs"]) == ["p-alice"]
    assert sorted(rows["sentences"]) == ["s-alice"]


def test_an_accounts_manuscript_is_invisible_to_another_account(services, neo4j_session):
    _alice_manuscript(services)
    try:
        chapter_repo = services["repos"][Chapter]
        paragraph_repo = services["repos"][Paragraph]
        sentence_repo = services["repos"][Sentence]

        assert [row["id"] for row in services["chapter"].list_by_document("d-alice", owner=_ALICE)] == ["c-alice"]
        assert chapter_repo.load("c-alice", _ALICE) is not None
        assert chapter_repo.find_document_id("c-alice", _ALICE) == "d-alice"

        assert [row["id"] for row in services["paragraph"].list_by_chapter("c-alice", owner=_ALICE)] == ["p-alice"]
        assert paragraph_repo.load("p-alice", _ALICE) is not None
        assert [row["id"] for row in services["sentence"].list_by_paragraph("p-alice", owner=_ALICE)] == ["s-alice"]
        assert sentence_repo.load("s-alice", _ALICE) is not None

        assert services["chapter"].list_by_document("d-alice", owner=_BOB) == []
        assert chapter_repo.load("c-alice", _BOB) is None
        assert chapter_repo.find_document_id("c-alice", _BOB) is None

        assert services["paragraph"].list_by_chapter("c-alice", owner=_BOB) == []
        assert paragraph_repo.load("p-alice", _BOB) is None
        assert sentence_repo.load("s-alice", _BOB) is None
        assert services["sentence"].list_by_paragraph("p-alice", owner=_BOB) == []
    finally:
        neo4j_session.run(_CLEANUP_CYPHER, {"ids": ["d-alice"]})


def test_another_account_cannot_write_into_a_manuscript_it_cannot_see(services, neo4j_session):
    _alice_manuscript(services)
    try:
        assert services["chapter"].update("c-alice", title="Stolen", owner=_BOB) is None
        assert services["paragraph"].update("p-alice", content=[], owner=_BOB) is None
        assert services["sentence"].update("s-alice", text="Stolen", owner=_BOB) is None
        assert services["chapter"].delete("c-alice", owner=_BOB) is False
        assert services["paragraph"].delete("p-alice", owner=_BOB) is False
        assert services["sentence"].delete("s-alice", owner=_BOB) is False

        assert services["chapter"].get("c-alice", owner=_ALICE).title == "Intro"
        assert services["sentence"].get("s-alice", owner=_ALICE).text == ""

        with pytest.raises(ChapterNotFoundError):
            services["paragraph"].create("p-bob", content=[], chapter_id="c-alice", owner=_BOB)
        with pytest.raises(ParagraphNotFoundError):
            services["sentence"].create("s-bob", text="Intruder", paragraph_id="p-alice", owner=_BOB)
        with pytest.raises(DocumentNotFoundError):
            services["chapter"].create("c-bob", "Intruder", document_id="d-never-existed", owner=_BOB)

        assert services["paragraph"].list_by_chapter("c-alice", owner=_ALICE) == [{"id": "p-alice"}]
        assert services["sentence"].list_by_paragraph("p-alice", owner=_ALICE) == [{"id": "s-alice"}]
        _assert_nothing_was_created(neo4j_session, "d-alice")
    finally:
        neo4j_session.run(_CLEANUP_CYPHER, {"ids": ["d-alice"]})


def test_a_chapter_cannot_be_created_in_another_accounts_document(services, neo4j_session):
    services["document"].create("d-alice", title="Opening", author="Alice", owner=_ALICE)
    try:
        with pytest.raises(DocumentNotFoundError):
            services["chapter"].create("c-bob", "Intruder", document_id="d-alice", owner=_BOB)

        assert services["chapter"].list_by_document("d-alice", owner=_ALICE) == []
        assert (
            neo4j_session.run(
                "MATCH (:Document {id: $id})<-[:PART_OF]-(c:Chapter) RETURN count(c) AS chapters",
                {"id": "d-alice"},
            ).single()["chapters"]
            == 0
        )
    finally:
        neo4j_session.run(_CLEANUP_CYPHER, {"ids": ["d-alice"]})
