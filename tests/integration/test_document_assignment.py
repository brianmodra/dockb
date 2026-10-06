"""Integration test: assigning a document makes it reachable, tree and all.

The unit tests prove the service asks the right questions and moves the right files; this
drives the real graph, so it proves the properties those assertions stand for — an unowned
document belongs to nobody until this command gives it an account, the graph's own
``(owner, title_key)`` constraint refuses the collision the service refuses first, and the
account's own repository ends up holding the files.
"""

import pytest

from dockb.exceptions import DuplicateTitleError
from dockb.infrastructure.document_store.factory import DocumentStoreFactory
from dockb.repositories.document_repository import DocumentRepository
from dockb.services.assignment_service import DocumentAssignmentService

pytestmark = pytest.mark.integration

_ALICE = "acct-assign-alice"
_BOB = "acct-assign-bob"

# A document with no owner property at all, which is what one created before accounts
# owned manuscripts looks like. Written as raw Cypher because every repository write
# stamps an owner.
_CREATE_UNOWNED_CYPHER = """
CREATE (d:Document {id: $id, title: $title, author: $author, title_key: $title_key})
"""

_CLEANUP_CYPHER = """
MATCH (d:Document)
WHERE d.id IN $ids
OPTIONAL MATCH (c:Chapter)-[:PART_OF]->(d)
OPTIONAL MATCH (p:Paragraph)-[:PART_OF]->(c)
OPTIONAL MATCH (s:Sentence)-[:PART_OF]->(p)
OPTIONAL MATCH (t:Token)-[:PART_OF]->(s)
DETACH DELETE d, c, p, s, t
"""


@pytest.fixture(autouse=True)
def _git_identity(monkeypatch):
    monkeypatch.setenv("GIT_AUTHOR_NAME", "Test")
    monkeypatch.setenv("GIT_AUTHOR_EMAIL", "test@test.com")
    monkeypatch.setenv("GIT_COMMITTER_NAME", "Test")
    monkeypatch.setenv("GIT_COMMITTER_EMAIL", "test@test.com")


@pytest.fixture()
def assignment(neo4j_session, tmp_path):
    """The service over the live graph and a real per-account store factory."""
    repo = DocumentRepository(neo4j_session)
    return DocumentAssignmentService(repo, DocumentStoreFactory(base_dir=tmp_path)), repo, tmp_path


def _make_unowned(neo4j_session, document_id: str, title: str) -> None:
    neo4j_session.run(
        _CREATE_UNOWNED_CYPHER,
        {"id": document_id, "title": title, "author": "Nobody", "title_key": title.lower()},
    )


def _write_flat_tree(base, title: str, body: str) -> None:
    chapter = base / title / "Act I" / "One.md"
    chapter.parent.mkdir(parents=True, exist_ok=True)
    chapter.write_text(body, encoding="utf-8")


def test_an_unowned_document_belongs_to_nobody_until_it_is_assigned(assignment, neo4j_session):
    service, repo, _base = assignment
    try:
        _make_unowned(neo4j_session, "d-orphan", "Orphan")

        assert repo.find_summary("d-orphan")["owner"] is None
        assert repo.list_all(_ALICE) == []
        assert repo.load_shell("d-orphan", _ALICE) is None

        service.assign("d-orphan", _ALICE)

        assert repo.find_summary("d-orphan")["owner"] == _ALICE
        assert [row["id"] for row in repo.list_all(_ALICE)] == ["d-orphan"]
        assert repo.load_shell("d-orphan", _ALICE) is not None
    finally:
        neo4j_session.run(_CLEANUP_CYPHER, {"ids": ["d-orphan"]})


def test_a_document_whose_owner_is_the_empty_string_is_listed_too(assignment, neo4j_session):
    """The older spelling of "nobody", which ``repair_empty_document_owners.cypher`` exists for.

    A build that defaulted ``Document.owner`` to ``""`` wrote that string into the graph.
    Such a document is in nobody's library and cannot be deleted, renamed or handed over
    from the editor, so unless assignment lists it, it stays unreachable forever.
    """
    service, repo, _base = assignment
    try:
        neo4j_session.run(
            "CREATE (d:Document {id: 'd-empty', title: 'Empty', author: 'Nobody', owner: '', title_key: 'empty'})",
        )

        assert "d-empty" in {row["id"] for row in repo.list_unowned()}

        service.assign("d-empty", _ALICE)

        assert repo.find_summary("d-empty")["owner"] == _ALICE
    finally:
        neo4j_session.run(_CLEANUP_CYPHER, {"ids": ["d-empty"]})


def test_assignment_does_not_rewrite_the_documents_author(assignment, neo4j_session):
    """Ownership is the account; ``author`` is what the manuscript says about itself.

    It may be a pen name, or a collaborator, or nobody at all. A transfer moves the
    document between accounts and leaves the byline alone.
    """
    service, repo, _base = assignment
    try:
        _make_unowned(neo4j_session, "d-author", "Faith")

        service.assign("d-author", _ALICE)

        assert repo.load_shell("d-author", _ALICE).author == "Nobody"
    finally:
        neo4j_session.run(_CLEANUP_CYPHER, {"ids": ["d-author"]})


def test_it_stops_being_listed_as_unowned(assignment, neo4j_session):
    service, repo, _base = assignment
    try:
        _make_unowned(neo4j_session, "d-orphan", "Orphan")
        assert "d-orphan" in {row["id"] for row in repo.list_unowned()}

        service.assign("d-orphan", _ALICE)

        assert "d-orphan" not in {row["id"] for row in repo.list_unowned()}
    finally:
        neo4j_session.run(_CLEANUP_CYPHER, {"ids": ["d-orphan"]})


def test_the_assigned_documents_markdown_lands_in_the_accounts_tree(assignment, neo4j_session):
    """The whole point: the files an operator wrote on disk are in the new owner's tree."""
    service, _repo, base = assignment
    try:
        _make_unowned(neo4j_session, "d-orphan", "Orphan")
        _write_flat_tree(base, "Orphan", "# the chapter nobody imported\n")

        service.assign("d-orphan", _ALICE)

        adopted = base / _ALICE / "Orphan" / "Act I" / "One.md"
        assert adopted.read_text(encoding="utf-8") == "# the chapter nobody imported\n"
        assert not (base / "Orphan").exists()
    finally:
        neo4j_session.run(_CLEANUP_CYPHER, {"ids": ["d-orphan"]})


def test_a_title_the_account_already_holds_is_refused_and_the_graph_is_untouched(assignment, neo4j_session):
    """The service refuses first; the graph's own constraint would refuse it too.

    Writing the refusal this way round matters: if the service ever stopped checking, the
    constraint would still hold — a document nobody owns cannot become a second document
    with a title the account already has.
    """
    service, repo, _base = assignment
    try:
        _make_unowned(neo4j_session, "d-his", "Faith")
        service.assign("d-his", _ALICE)
        _make_unowned(neo4j_session, "d-theirs", "Faith")

        with pytest.raises(DuplicateTitleError):
            service.assign("d-theirs", _ALICE)

        assert repo.find_summary("d-theirs")["owner"] is None
        assert [row["id"] for row in repo.list_all(_ALICE)] == ["d-his"]
    finally:
        neo4j_session.run(_CLEANUP_CYPHER, {"ids": ["d-his", "d-theirs"]})


def test_a_document_can_be_moved_between_accounts(assignment, neo4j_session):
    """The recovery case: one account's manuscript, given to another.

    Two accounts may each hold a document of the same title, so this is not the clash
    above — the graph's constraint is per owner, and the trees are separate directories.
    """
    service, repo, base = assignment
    try:
        _make_unowned(neo4j_session, "d-move", "Faith")
        service.assign("d-move", _BOB)
        original = base / _BOB / "Faith" / "Act I" / "One.md"
        original.parent.mkdir(parents=True, exist_ok=True)
        original.write_text("# bob's copy\n", encoding="utf-8")

        service.assign("d-move", _ALICE)

        assert [row["id"] for row in repo.list_all(_BOB)] == []
        assert [row["id"] for row in repo.list_all(_ALICE)] == ["d-move"]
        assert (base / _ALICE / "Faith" / "Act I" / "One.md").is_file()
        assert not original.exists()
    finally:
        neo4j_session.run(_CLEANUP_CYPHER, {"ids": ["d-move"]})
