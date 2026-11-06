"""Tests for MentionsRepository — the four paragraph states and their writes."""

from unittest.mock import MagicMock

import pytest

from dockb.repositories.mentions_repository import MentionsRepository

_OWNER = "acct-1"


def extract_call(mock_session: MagicMock, call_index: int = 0):
    call = mock_session.run.call_args_list[call_index]
    params = call.args[1] if len(call.args) > 1 else call.kwargs
    return call.args[0], params


@pytest.fixture()
def repo(neo4j_session):
    return MentionsRepository(neo4j_session)


class TestParagraphStates:
    """The state query: every paragraph of a scope with its state number."""

    def test_lists_a_chapters_paragraphs_with_states(self, repo, neo4j_session):
        neo4j_session.run.return_value = [
            {"id": "p1", "index": 0, "checked_at": None, "mentions": []},
            {"id": "p2", "index": 1, "checked_at": 1, "mentions": []},
            {"id": "p3", "index": 2, "checked_at": 1, "mentions": [{"character_id": "k1", "stale": False}]},
            {"id": "p4", "index": 3, "checked_at": 1, "mentions": [{"character_id": "k1", "stale": True}]},
        ]

        states = repo.paragraph_states(chapter_id="c1", owner=_OWNER)

        assert states == [
            {"id": "p1", "state": 1, "index": 0, "mentions": []},
            {"id": "p2", "state": 2, "index": 1, "mentions": []},
            {"id": "p3", "state": 3, "index": 2, "mentions": ["k1"]},
            {"id": "p4", "state": 4, "index": 3, "mentions": []},
        ]
        cypher, params = extract_call(neo4j_session)
        assert "Chapter {id: $chapter_id}" in cypher
        assert "owner: $owner" in cypher
        assert params == {"chapter_id": "c1", "owner": _OWNER}

    def test_lists_a_documents_paragraphs_when_no_chapter_is_given(self, repo, neo4j_session):
        neo4j_session.run.return_value = [{"id": "p1", "checked_at": None, "mentions": []}]

        repo.paragraph_states(document_id="d1", owner=_OWNER)

        cypher, params = extract_call(neo4j_session)
        assert "Document {id: $document_id" in cypher
        assert params["document_id"] == "d1"

    def test_a_paragraph_with_any_stale_mention_is_state_4(self, repo, neo4j_session):
        neo4j_session.run.return_value = [
            {
                "id": "p1",
                "checked_at": 1,
                "mentions": [
                    {"character_id": "k1", "stale": False},
                    {"character_id": "k2", "stale": True},
                ],
            }
        ]

        states = repo.paragraph_states(chapter_id="c1", owner=_OWNER)

        assert states == [{"id": "p1", "state": 4, "index": 0, "mentions": []}]


class TestStampVerdicts:
    """Stamping replaces a paragraph's verdicts wholesale and stamps it checked."""

    def test_deletes_old_mentions_and_writes_the_fresh_set(self, repo, neo4j_session):
        repo.stamp(
            "p1",
            [{"character_id": "k1", "method": "name", "confidence": 1.0}],
            owner=_OWNER,
            checked_at="2026-11-05T00:00:00Z",
        )

        cypher, params = extract_call(neo4j_session)
        assert "DETACH DELETE" not in cypher  # the delete is of RELATIONSHIPS only
        assert "DELETE m" in cypher
        assert "owner: $owner" in cypher
        assert "mentions_checked_at = $checked_at" in cypher
        assert params["paragraph_id"] == "p1"
        assert params["owner"] == _OWNER
        assert params["checked_at"] == "2026-11-05T00:00:00Z"
        assert params["verdicts"] == [{"character_id": "k1", "method": "name", "confidence": 1.0}]

    def test_a_partial_tier_1_write_carries_owner_but_no_stamp(self, repo, neo4j_session):
        repo.stamp("p1", [{"character_id": "k1", "method": "name", "confidence": 1.0}], owner=_OWNER)

        _, params = extract_call(neo4j_session)
        assert params["owner"] == _OWNER
        assert params["checked_at"] is None

    def test_stamping_no_verdicts_leaves_a_state_2_paragraph(self, repo, neo4j_session):
        repo.stamp("p1", [], owner=_OWNER, checked_at="2026-11-05T00:00:00Z")

        _, params = extract_call(neo4j_session)
        assert params["verdicts"] == []
        assert params["owner"] == _OWNER
        assert params["checked_at"] == "2026-11-05T00:00:00Z"


class TestMarkStale:
    """Invalidation marks relationships stale, and un-stamps the no-mention verdicts."""

    def test_marks_a_chapters_mentions_stale(self, repo, neo4j_session):
        repo.mark_stale(chapter_id="c1", owner=_OWNER)

        cypher, params = extract_call(neo4j_session)
        assert "stale = true" in cypher
        assert "Chapter {id: $chapter_id}" in cypher
        assert params == {"chapter_id": "c1", "owner": _OWNER}

    def test_marks_a_whole_document_stale(self, repo, neo4j_session):
        repo.mark_stale(document_id="d1", owner=_OWNER)

        cypher, params = extract_call(neo4j_session)
        assert "Document {id: $document_id" in cypher
        assert params == {"document_id": "d1", "owner": _OWNER}

    def test_state_2_paragraphs_lose_their_stamp_so_they_return_to_state_1(self, repo, neo4j_session):
        repo.mark_stale(chapter_id="c1", owner=_OWNER)

        cypher, _ = extract_call(neo4j_session)
        assert "mentions_checked_at = null" in cypher


class TestChapterRollup:
    """The chapter's own MENTIONS: a view over its paragraphs' valid verdicts."""

    def test_stamp_chapter_replaces_the_chapters_mentions(self, repo, neo4j_session):
        repo.stamp_chapter("c1", ["k1", "k2"], owner=_OWNER)

        cypher, params = extract_call(neo4j_session)
        assert "MATCH (ch:Chapter {id: $chapter_id})-[:PART_OF]->(d:Document {owner: $owner})" in cypher
        assert "DELETE m" in cypher
        assert params["character_ids"] == ["k1", "k2"]

    def test_mark_stale_also_stales_the_chapters_rollup(self, repo, neo4j_session):
        repo.mark_stale(chapter_id="c1", owner=_OWNER)

        cypher, _ = extract_call(neo4j_session)
        assert "(ch)-[cm:MENTIONS" in cypher
        assert "cm.stale = true" in cypher
