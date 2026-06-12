"""Tests for ParagraphRepository."""

from typing import Any
from unittest.mock import MagicMock

import pytest

from dockb.models.base import DataState
from dockb.models.sentence import Sentence

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def extract_call(mock_session: MagicMock, call_index: int = 0) -> tuple[str, dict[str, Any]]:
    """Return (cypher, params_dict) from the *call_index*-th session.run() call."""
    call = mock_session.run.call_args_list[call_index]
    cypher: str = call.args[0]
    if len(call.args) > 1:
        params: dict[str, Any] = call.args[1]
    else:
        params = call.kwargs
    return cypher, params


def assert_child_dict(actual: dict[str, Any], expected: dict[str, Any], index: int) -> None:
    for key, val in expected.items():
        assert actual[key] == val, f"child[{index}].{key}"
    assert actual.get("index") == index, f"child[{index}].index"


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestSaveNewParagraph:
    """Behaviour when paragraph.state == DataState.NEW."""

    def test_merges_paragraph_node_and_unwinds_sentences(self, paragraph_repo, neo4j_session, paragraph):
        paragraph.state = DataState.NEW
        paragraph.sentences.append(Sentence(text="Hello world."))

        paragraph_repo.save(paragraph, chapter_id="ch1")

        cypher, _ = extract_call(neo4j_session)
        assert "MATCH (c:Chapter" in cypher
        assert "MERGE (p:Paragraph" in cypher
        assert "UNWIND $sentences" in cypher
        assert "MERGE (sent:Sentence" in cypher
        assert "MERGE (sent)-[r:PART_OF]->(p)" in cypher
        assert "SET r.index" in cypher

    def test_passes_chapter_and_paragraph_ids(self, paragraph_repo, neo4j_session, paragraph):
        paragraph.state = DataState.NEW
        paragraph_repo.save(paragraph, chapter_id="ch1")

        _, params = extract_call(neo4j_session)
        assert params["chapter_id"] == "ch1"
        assert params["paragraph_id"] == paragraph.id

    def test_passes_sentence_ids(self, paragraph_repo, neo4j_session, paragraph):
        paragraph.state = DataState.NEW
        sent = Sentence(text="Hello world.")
        paragraph.sentences.append(sent)

        paragraph_repo.save(paragraph, chapter_id="ch1")

        _, params = extract_call(neo4j_session)
        sentences = params["sentences"]
        assert len(sentences) == 1
        assert sentences[0]["id"] == sent.id
        assert "text" not in sentences[0]

    def test_preserves_sentence_order(self, paragraph_repo, neo4j_session, paragraph):
        paragraph.state = DataState.NEW
        sent_a = Sentence(text="First.")
        sent_b = Sentence(text="Second.")
        paragraph.sentences.append(sent_a)
        paragraph.sentences.append(sent_b)

        paragraph_repo.save(paragraph, chapter_id="ch1")

        _, params = extract_call(neo4j_session)
        sentences = params["sentences"]
        assert len(sentences) == 2
        assert sentences[0]["id"] == sent_a.id
        assert sentences[0]["index"] == 0
        assert sentences[1]["id"] == sent_b.id
        assert sentences[1]["index"] == 1

    def test_does_not_include_orphan_cleanup(self, paragraph_repo, neo4j_session, paragraph):
        paragraph.state = DataState.NEW
        paragraph.sentences.append(Sentence(text="Hello."))

        paragraph_repo.save(paragraph, chapter_id="ch1")

        cypher, _ = extract_call(neo4j_session)
        assert "OPTIONAL MATCH" not in cypher or "DETACH DELETE" not in cypher


class TestSaveChangedParagraph:
    """Behaviour when paragraph.state == DataState.CHANGED."""

    def test_includes_orphan_cleanup(self, paragraph_repo, neo4j_session, paragraph):
        paragraph.state = DataState.CHANGED
        paragraph.sentences.append(Sentence(text="Hello."))

        paragraph_repo.save(paragraph, chapter_id="ch1")

        cypher, _ = extract_call(neo4j_session)
        assert "OPTIONAL MATCH" in cypher
        assert "DETACH DELETE orphan" in cypher

    def test_passes_only_current_sentences_after_removal(self, paragraph_repo, neo4j_session, paragraph):
        paragraph.state = DataState.CHANGED
        sent_a = Sentence(text="Hello.")
        sent_b = Sentence(text="Goodbye.")
        paragraph.sentences.append(sent_a)
        paragraph.sentences.append(sent_b)
        paragraph.delete_child(sent_a.id)

        paragraph_repo.save(paragraph, chapter_id="ch1")

        _, params = extract_call(neo4j_session)
        sentences = params["sentences"]
        assert len(sentences) == 1
        assert sentences[0]["id"] == sent_b.id
        assert sentences[0]["index"] == 0


class TestSaveDeletedParagraph:  # pylint: disable=too-few-public-methods
    """Behaviour when paragraph.state == DataState.DELETED."""

    def test_detach_deletes_the_paragraph(self, paragraph_repo, neo4j_session, paragraph):
        paragraph.state = DataState.DELETED
        paragraph_repo.save(paragraph, chapter_id="ch1")

        cypher, params = extract_call(neo4j_session)
        assert "DETACH DELETE" in cypher
        assert params["paragraph_id"] == paragraph.id


class TestSaveSkipStates:  # pylint: disable=too-few-public-methods
    """States that should NOT call session.run()."""

    @pytest.mark.parametrize("state", [DataState.SYNC, DataState._])
    def test_skips_run(self, state, paragraph_repo, neo4j_session, paragraph):
        paragraph.state = state
        paragraph_repo.save(paragraph, chapter_id="ch1")
        neo4j_session.run.assert_not_called()


class TestSaveDirtyParagraph:  # pylint: disable=too-few-public-methods
    """Dirty flag guard."""

    def test_raises_value_error(self, paragraph_repo, neo4j_session, paragraph):
        paragraph.dirty = True
        paragraph.state = DataState.CHANGED
        with pytest.raises(ValueError, match="(?i)dirty"):
            paragraph_repo.save(paragraph, chapter_id="ch1")
        neo4j_session.run.assert_not_called()
