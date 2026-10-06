"""Tests for the shared ownership check used by the chapter, paragraph and sentence repositories."""

from unittest.mock import MagicMock

from dockb.repositories.ownership import owned_node_exists


def extract_call(mock_session: MagicMock, call_index: int = 0) -> tuple[str, dict[str, object]]:
    """Return (cypher, params_dict) from the *call_index*-th session.run() call."""
    call = mock_session.run.call_args_list[call_index]
    cypher: str = call.args[0]
    if len(call.args) > 1:
        params: dict[str, object] = call.args[1]
    else:
        params = call.kwargs
    return cypher, params


class TestOwnedNodeExists:
    def test_true_when_the_chain_reaches_an_owned_document(self, neo4j_session):
        neo4j_session.run.return_value = [{"owned": 1}]

        assert owned_node_exists(neo4j_session, "Chapter", "ch-1", "acct-1") is True

    def test_false_when_the_document_belongs_to_another_account(self, neo4j_session):
        neo4j_session.run.return_value = [{"owned": 0}]

        assert owned_node_exists(neo4j_session, "Chapter", "ch-1", "acct-1") is False

    def test_false_when_the_query_returns_no_record(self, neo4j_session):
        neo4j_session.run.return_value = []

        assert owned_node_exists(neo4j_session, "Chapter", "ch-1", "acct-1") is False

    def test_scopes_by_owner_and_bounds_the_walk(self, neo4j_session):
        neo4j_session.run.return_value = [{"owned": 0}]

        owned_node_exists(neo4j_session, "Sentence", "s-1", "acct-1")

        cypher, params = extract_call(neo4j_session)
        assert "[:PART_OF*1..3]" in cypher
        assert "->(d:Document {owner: $owner})" in cypher
        assert params == {"id": "s-1", "owner": "acct-1"}

    def test_matches_only_the_requested_label(self, neo4j_session):
        neo4j_session.run.return_value = [{"owned": 0}]

        owned_node_exists(neo4j_session, "Paragraph", "p-1", "acct-1")

        cypher, _ = extract_call(neo4j_session)
        assert "(n:Paragraph {id: $id})" in cypher
        assert "Chapter" not in cypher
