"""Integration test: the mentions repository's stamping against a live graph.

The stamp is one Cypher statement whose row semantics matter: an empty verdict
list is the "mentions nobody" verdict and must still write the
``mentions_checked_at`` stamp (state 2). A mocked session only records the
parameters, so this test creates a document, chapter and paragraph in the real
graph and reads the states back through the repository.
"""

import pytest

from dockb.repositories.mentions_repository import MentionsRepository

pytestmark = pytest.mark.integration

OWNER = "acct-test-mentions-repository"
DOCUMENT_ID = "d-test-mentions-repository"
CHAPTER_ID = "c-test-mentions-repository"
PARAGRAPH_ID = "p-test-mentions-repository"
CHARACTER_ID = "k-test-mentions-repository"

_CHECKED_AT = "2026-11-05T00:00:00Z"

_CLEANUP_CYPHER = """
MATCH (d:Document {id: $document_id, owner: $owner})
OPTIONAL MATCH (ch:Chapter)-[:PART_OF]->(d)
OPTIONAL MATCH (p:Paragraph)-[:PART_OF]->(ch)
DETACH DELETE d, ch, p
"""

_SETUP_DOCUMENT_CYPHER = """
MERGE (d:Document {id: $document_id, owner: $owner})
MERGE (ch:Chapter {id: $chapter_id, category: 'Chapter'})
MERGE (p:Paragraph {id: $paragraph_id})
MERGE (ch)-[:PART_OF {index: 0}]->(d)
MERGE (p)-[:PART_OF {index: 0}]->(ch)
"""

_SETUP_CHARACTER_CYPHER = """
MERGE (d:Document {id: $document_id, owner: $owner})
MERGE (k:Chapter {id: $character_id, category: 'Character'})
MERGE (k)-[:PART_OF {index: 0}]->(d)
"""

_PARAMS = {"document_id": DOCUMENT_ID, "chapter_id": CHAPTER_ID, "paragraph_id": PARAGRAPH_ID, "owner": OWNER}


@pytest.fixture()
def repo(neo4j_session):
    """A repository over a fresh document/chapter/paragraph, cleaned up either side."""
    neo4j_session.run(_CLEANUP_CYPHER, _PARAMS)
    neo4j_session.run(_SETUP_DOCUMENT_CYPHER, _PARAMS)
    yield MentionsRepository(neo4j_session)
    neo4j_session.run(_CLEANUP_CYPHER, _PARAMS)


def _states(repo: MentionsRepository) -> list[dict[str, object]]:
    return repo.paragraph_states(OWNER, chapter_id=CHAPTER_ID)


def test_stamping_no_verdicts_moves_a_paragraph_to_state_2(repo):
    repo.stamp(PARAGRAPH_ID, [], owner=OWNER, checked_at=_CHECKED_AT)

    assert _states(repo) == [{"id": PARAGRAPH_ID, "state": 2, "index": 0, "mentions": []}]


def test_stamping_no_verdicts_replaces_existing_mentions(repo, neo4j_session):
    neo4j_session.run(_SETUP_CHARACTER_CYPHER, {**_PARAMS, "character_id": CHARACTER_ID})
    repo.stamp(
        PARAGRAPH_ID,
        [{"character_id": CHARACTER_ID, "method": "name", "confidence": 1.0}],
        owner=OWNER,
        checked_at=_CHECKED_AT,
    )
    assert _states(repo)[0]["state"] == 3

    repo.stamp(PARAGRAPH_ID, [], owner=OWNER, checked_at=_CHECKED_AT)

    assert _states(repo)[0]["state"] == 2
