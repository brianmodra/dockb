"""Tests for DocumentRepository."""

from typing import Any
from unittest.mock import MagicMock

import pytest

from dockb.models.base import DataState
from dockb.models.chapter import Chapter

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


class TestSaveNewDocument:
    """Behaviour when document.state == DataState.NEW."""

    def test_merges_document_node_and_unwinds_chapters(self, document_repo, neo4j_session, document):
        document.state = DataState.NEW
        document.chapters.append(Chapter(text="First chapter."))

        document_repo.save(document)

        cypher, _ = extract_call(neo4j_session)
        assert "MERGE (d:Document" in cypher
        assert "UNWIND $chapters" in cypher
        assert "MERGE (chapter:Chapter" in cypher
        assert "MERGE (chapter)-[r:PART_OF]->(d)" in cypher
        assert "SET r.index" in cypher

    def test_passes_document_id(self, document_repo, neo4j_session, document):
        document.state = DataState.NEW
        document_repo.save(document)

        _, params = extract_call(neo4j_session)
        assert params["document_id"] == document.id

    def test_passes_chapter_ids(self, document_repo, neo4j_session, document):
        document.state = DataState.NEW
        chap = Chapter(text="First chapter.")
        document.chapters.append(chap)

        document_repo.save(document)

        _, params = extract_call(neo4j_session)
        chapters = params["chapters"]
        assert len(chapters) == 1
        assert chapters[0]["id"] == chap.id
        assert "text" not in chapters[0]

    def test_preserves_chapter_order(self, document_repo, neo4j_session, document):
        document.state = DataState.NEW
        chap_a = Chapter(text="First.")
        chap_b = Chapter(text="Second.")
        document.chapters.append(chap_a)
        document.chapters.append(chap_b)

        document_repo.save(document)

        _, params = extract_call(neo4j_session)
        chapters = params["chapters"]
        assert len(chapters) == 2
        assert chapters[0]["id"] == chap_a.id
        assert chapters[0]["index"] == 0
        assert chapters[1]["id"] == chap_b.id
        assert chapters[1]["index"] == 1

    def test_does_not_include_orphan_cleanup(self, document_repo, neo4j_session, document):
        document.state = DataState.NEW
        document.chapters.append(Chapter(text="Hello."))

        document_repo.save(document)

        cypher, _ = extract_call(neo4j_session)
        assert "OPTIONAL MATCH" not in cypher or "DETACH DELETE" not in cypher


class TestSaveChangedDocument:
    """Behaviour when document.state == DataState.CHANGED."""

    def test_includes_orphan_cleanup(self, document_repo, neo4j_session, document):
        document.state = DataState.CHANGED
        document.chapters.append(Chapter(text="Hello."))

        document_repo.save(document)

        cypher, _ = extract_call(neo4j_session)
        assert "OPTIONAL MATCH" in cypher
        assert "DETACH DELETE orphan" in cypher

    def test_passes_only_current_chapters_after_removal(self, document_repo, neo4j_session, document):
        document.state = DataState.CHANGED
        chap_a = Chapter(text="Hello.")
        chap_b = Chapter(text="Goodbye.")
        document.chapters.append(chap_a)
        document.chapters.append(chap_b)
        document.delete_child(chap_a.id)

        document_repo.save(document)

        _, params = extract_call(neo4j_session)
        chapters = params["chapters"]
        assert len(chapters) == 1
        assert chapters[0]["id"] == chap_b.id
        assert chapters[0]["index"] == 0


class TestSaveDeletedDocument:  # pylint: disable=too-few-public-methods
    """Behaviour when document.state == DataState.DELETED."""

    def test_detach_deletes_the_document(self, document_repo, neo4j_session, document):
        document.state = DataState.DELETED
        document_repo.save(document)

        cypher, params = extract_call(neo4j_session)
        assert "DETACH DELETE" in cypher
        assert params["document_id"] == document.id


class TestSaveSkipStates:  # pylint: disable=too-few-public-methods
    """States that should NOT call session.run()."""

    @pytest.mark.parametrize("state", [DataState.SYNC, DataState._])
    def test_skips_run(self, state, document_repo, neo4j_session, document):
        document.state = state
        document_repo.save(document)
        neo4j_session.run.assert_not_called()


class TestSaveDirtyDocument:  # pylint: disable=too-few-public-methods
    """Dirty flag guard."""

    def test_raises_value_error(self, document_repo, neo4j_session, document):
        document.dirty = True
        document.state = DataState.CHANGED
        with pytest.raises(ValueError, match="(?i)dirty"):
            document_repo.save(document)
        neo4j_session.run.assert_not_called()
