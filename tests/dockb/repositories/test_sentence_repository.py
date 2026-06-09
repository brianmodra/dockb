"""Tests for SentenceRepository."""

from unittest.mock import MagicMock

import pytest
from neo4j import Session

from dockb.models.base import DataState
from dockb.models.sentence import Sentence
from dockb.models.token import POS, Token, Type


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def extract_call(mock_session, call_index=0):
    """Return (cypher, params_dict) from the *call_index*-th session.run() call."""
    call = mock_session.run.call_args_list[call_index]
    cypher = call.args[0]
    # Params may be a second positional arg or spread as kwargs
    if len(call.args) > 1:
        params = call.args[1]
    else:
        params = call.kwargs
    return cypher, params


# ---------------------------------------------------------------------------
# Token-level param assertions (shared by NEW and CHANGED tests)
# ---------------------------------------------------------------------------

TOKEN_A_DICT = dict(
    text="Hello",
    trailing_ws=" ",
    type="word",
    pos="PROPN",
    lemma="hello",
    is_alpha=True,
    is_digit=False,
    like_num=False,
    is_stop=False,
)

TOKEN_B_DICT = dict(
    text="world",
    trailing_ws="",
    type="word",
    pos="NOUN",
    lemma="world",
    is_alpha=True,
    is_digit=False,
    like_num=False,
    is_stop=False,
)


def assert_token_dict(actual, expected, index):
    for key, val in expected.items():
        assert actual[key] == val, f"token[{index}].{key}"
    assert actual.get("index") == index, f"token[{index}].index"


def make_token(text, type_=Type.WORD, **kw):
    """Build a Token with sensible defaults for repo tests."""
    return Token(text=text, type=type_, **kw)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestSaveNewSentence:
    """Behaviour when sentence.state == DataState.NEW."""

    def test_merges_sentence_node_and_unwinds_tokens(self, repo, neo4j_session, sentence):
        sentence.state = DataState.NEW
        sentence.tokens.append(make_token("Hello"))

        repo.save(sentence, paragraph_id="p1")

        cypher, _ = extract_call(neo4j_session)
        assert "MATCH (p:Paragraph" in cypher
        assert "MERGE (s:Sentence" in cypher
        assert "UNWIND $tokens" in cypher
        assert "MERGE (tok:Token" in cypher
        assert "ON CREATE SET" in cypher
        assert "ON MATCH SET" in cypher
        assert "MERGE (tok)-[r:PART_OF]->(s)" in cypher or "CREATE (tok)-[:PART_OF]->(s)" in cypher

    def test_passes_paragraph_and_sentence_ids(self, repo, neo4j_session, sentence):
        sentence.state = DataState.NEW
        repo.save(sentence, paragraph_id="p1")

        _, params = extract_call(neo4j_session)
        assert params["paragraph_id"] == "p1"
        assert params["sentence_id"] == sentence.id

    def test_passes_token_params(self, repo, neo4j_session, sentence):
        sentence.state = DataState.NEW
        sentence.tokens.append(make_token("Hello", pos=POS.PROPN, lemma="hello", is_alpha=True))

        repo.save(sentence, paragraph_id="p1")

        _, params = extract_call(neo4j_session)
        tokens = params["tokens"]
        assert len(tokens) == 1
        assert_token_dict(tokens[0], TOKEN_A_DICT, index=0)

    def test_preserves_token_order(self, repo, neo4j_session, sentence):
        sentence.state = DataState.NEW
        sentence.tokens.append(make_token("Hello", pos=POS.PROPN, lemma="hello", is_alpha=True))
        sentence.tokens.append(make_token("world", pos=POS.NOUN, lemma="world", is_alpha=True))

        repo.save(sentence, paragraph_id="p1")

        _, params = extract_call(neo4j_session)
        tokens = params["tokens"]
        assert len(tokens) == 2
        assert_token_dict(tokens[0], TOKEN_A_DICT, index=0)
        assert_token_dict(tokens[1], TOKEN_B_DICT, index=1)

    def test_does_not_include_orphan_cleanup(self, repo, neo4j_session, sentence):
        sentence.state = DataState.NEW
        sentence.tokens.append(make_token("Hello"))

        repo.save(sentence, paragraph_id="p1")

        cypher, _ = extract_call(neo4j_session)
        assert "OPTIONAL MATCH" not in cypher or "DETACH DELETE" not in cypher


class TestSaveChangedSentence:
    """Behaviour when sentence.state == DataState.CHANGED."""

    def test_includes_orphan_cleanup(self, repo, neo4j_session, sentence):
        sentence.state = DataState.CHANGED
        sentence.tokens.append(make_token("Hello"))

        repo.save(sentence, paragraph_id="p1")

        cypher, _ = extract_call(neo4j_session)
        assert "OPTIONAL MATCH" in cypher
        assert "DETACH DELETE orphan" in cypher

    def test_passes_current_tokens_only(self, repo, neo4j_session, sentence):
        sentence.state = DataState.CHANGED
        sentence.tokens.append(make_token("Hello", pos=POS.PROPN, lemma="hello", is_alpha=True))

        repo.save(sentence, paragraph_id="p1")

        _, params = extract_call(neo4j_session)
        assert len(params["tokens"]) == 1
        assert_token_dict(params["tokens"][0], TOKEN_A_DICT, index=0)


class TestSaveDeletedSentence:
    """Behaviour when sentence.state == DataState.DELETED."""

    def test_detach_deletes_the_sentence(self, repo, neo4j_session, sentence):
        sentence.state = DataState.DELETED
        repo.save(sentence, paragraph_id="p1")

        cypher, params = extract_call(neo4j_session)
        assert "DETACH DELETE" in cypher
        assert params["sentence_id"] == sentence.id


class TestSaveSkipStates:
    """States that should NOT call session.run()."""

    @pytest.mark.parametrize("state", [DataState.SYNC, DataState._])
    def test_skips_run(self, state, repo, neo4j_session, sentence):
        sentence.state = state
        repo.save(sentence, paragraph_id="p1")
        neo4j_session.run.assert_not_called()


class TestSaveDirtySentence:
    """Dirty flag guard."""

    def test_raises_value_error(self, repo, neo4j_session, sentence):
        sentence.dirty = True
        sentence.state = DataState.CHANGED
        with pytest.raises(ValueError, match="(?i)dirty"):
            repo.save(sentence, paragraph_id="p1")
        neo4j_session.run.assert_not_called()
