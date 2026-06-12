"""Tests for ChapterRepository."""

from typing import Any
from unittest.mock import MagicMock

import pytest

from dockb.models.base import DataState
from dockb.models.paragraph import Paragraph

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


class TestSaveNewChapter:
    """Behaviour when chapter.state == DataState.NEW."""

    def test_merges_chapter_node_and_unwinds_paragraphs(self, chapter_repo, neo4j_session, chapter):
        chapter.state = DataState.NEW
        chapter.paragraphs.append(Paragraph(text="First paragraph."))

        chapter_repo.save(chapter, document_id="d1")

        cypher, _ = extract_call(neo4j_session)
        assert "MATCH (d:Document" in cypher
        assert "MERGE (c:Chapter" in cypher
        assert "UNWIND $paragraphs" in cypher
        assert "MERGE (para:Paragraph" in cypher
        assert "MERGE (para)-[r:PART_OF]->(c)" in cypher
        assert "SET r.index" in cypher

    def test_passes_document_and_chapter_ids(self, chapter_repo, neo4j_session, chapter):
        chapter.state = DataState.NEW
        chapter_repo.save(chapter, document_id="d1")

        _, params = extract_call(neo4j_session)
        assert params["document_id"] == "d1"
        assert params["chapter_id"] == chapter.id

    def test_passes_paragraph_ids(self, chapter_repo, neo4j_session, chapter):
        chapter.state = DataState.NEW
        para = Paragraph(text="First paragraph.")
        chapter.paragraphs.append(para)

        chapter_repo.save(chapter, document_id="d1")

        _, params = extract_call(neo4j_session)
        paragraphs = params["paragraphs"]
        assert len(paragraphs) == 1
        assert paragraphs[0]["id"] == para.id
        assert "text" not in paragraphs[0]

    def test_preserves_paragraph_order(self, chapter_repo, neo4j_session, chapter):
        chapter.state = DataState.NEW
        para_a = Paragraph(text="First.")
        para_b = Paragraph(text="Second.")
        chapter.paragraphs.append(para_a)
        chapter.paragraphs.append(para_b)

        chapter_repo.save(chapter, document_id="d1")

        _, params = extract_call(neo4j_session)
        paragraphs = params["paragraphs"]
        assert len(paragraphs) == 2
        assert paragraphs[0]["id"] == para_a.id
        assert paragraphs[0]["index"] == 0
        assert paragraphs[1]["id"] == para_b.id
        assert paragraphs[1]["index"] == 1

    def test_does_not_include_orphan_cleanup(self, chapter_repo, neo4j_session, chapter):
        chapter.state = DataState.NEW
        chapter.paragraphs.append(Paragraph(text="Hello."))

        chapter_repo.save(chapter, document_id="d1")

        cypher, _ = extract_call(neo4j_session)
        assert "OPTIONAL MATCH" not in cypher or "DETACH DELETE" not in cypher


class TestSaveChangedChapter:
    """Behaviour when chapter.state == DataState.CHANGED."""

    def test_includes_orphan_cleanup(self, chapter_repo, neo4j_session, chapter):
        chapter.state = DataState.CHANGED
        chapter.paragraphs.append(Paragraph(text="Hello."))

        chapter_repo.save(chapter, document_id="d1")

        cypher, _ = extract_call(neo4j_session)
        assert "OPTIONAL MATCH" in cypher
        assert "DETACH DELETE orphan" in cypher

    def test_passes_only_current_paragraphs_after_removal(self, chapter_repo, neo4j_session, chapter):
        chapter.state = DataState.CHANGED
        para_a = Paragraph(text="Hello.")
        para_b = Paragraph(text="Goodbye.")
        chapter.paragraphs.append(para_a)
        chapter.paragraphs.append(para_b)
        chapter.delete_child(para_a.id)

        chapter_repo.save(chapter, document_id="d1")

        _, params = extract_call(neo4j_session)
        paragraphs = params["paragraphs"]
        assert len(paragraphs) == 1
        assert paragraphs[0]["id"] == para_b.id
        assert paragraphs[0]["index"] == 0


class TestSaveDeletedChapter:  # pylint: disable=too-few-public-methods
    """Behaviour when chapter.state == DataState.DELETED."""

    def test_detach_deletes_the_chapter(self, chapter_repo, neo4j_session, chapter):
        chapter.state = DataState.DELETED
        chapter_repo.save(chapter, document_id="d1")

        cypher, params = extract_call(neo4j_session)
        assert "DETACH DELETE" in cypher
        assert params["chapter_id"] == chapter.id


class TestSaveSkipStates:  # pylint: disable=too-few-public-methods
    """States that should NOT call session.run()."""

    @pytest.mark.parametrize("state", [DataState.SYNC, DataState._])
    def test_skips_run(self, state, chapter_repo, neo4j_session, chapter):
        chapter.state = state
        chapter_repo.save(chapter, document_id="d1")
        neo4j_session.run.assert_not_called()


class TestSaveDirtyChapter:  # pylint: disable=too-few-public-methods
    """Dirty flag guard."""

    def test_raises_value_error(self, chapter_repo, neo4j_session, chapter):
        chapter.dirty = True
        chapter.state = DataState.CHANGED
        with pytest.raises(ValueError, match="(?i)dirty"):
            chapter_repo.save(chapter, document_id="d1")
        neo4j_session.run.assert_not_called()
