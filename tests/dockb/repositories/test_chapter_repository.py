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
        assert "SET c.title = $title" in cypher
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
        assert params["title"] == chapter.title

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


# ---------------------------------------------------------------------------
# list_by_document
# ---------------------------------------------------------------------------


class TestListByDocument:
    """Behaviour of ChapterRepository.list_by_document()."""

    def test_returns_id_and_title(self, chapter_repo, neo4j_session):
        neo4j_session.run.return_value = [{"id": "ch-1", "title": "Chapter 1"}, {"id": "ch-2", "title": "Chapter 2"}]
        result = chapter_repo.list_by_document("d-1")
        assert result == [{"id": "ch-1", "title": "Chapter 1"}, {"id": "ch-2", "title": "Chapter 2"}]

    def test_returns_empty_list_when_no_chapters(self, chapter_repo, neo4j_session):
        neo4j_session.run.return_value = []
        result = chapter_repo.list_by_document("d-1")
        assert result == []

    def test_passes_document_id(self, chapter_repo, neo4j_session):
        neo4j_session.run.return_value = []
        chapter_repo.list_by_document("d-999")
        _, params = extract_call(neo4j_session)
        assert params["document_id"] == "d-999"

    def test_defaults_missing_title_to_empty(self, chapter_repo, neo4j_session):
        neo4j_session.run.return_value = [{"id": "ch-1", "title": None}]
        result = chapter_repo.list_by_document("d-1")
        assert result[0]["title"] == ""


# ---------------------------------------------------------------------------
# load
# ---------------------------------------------------------------------------


class TestLoadChapter:
    """Behaviour of ChapterRepository.load()."""

    def test_returns_none_when_not_found(self, chapter_repo, neo4j_session):
        neo4j_session.run.return_value = []
        assert chapter_repo.load("nonexistent") is None

    def test_returns_none_when_first_record_has_null_id(self, chapter_repo, neo4j_session):
        neo4j_session.run.return_value = [{"chapter_id": None}]
        assert chapter_repo.load("ch-1") is None

    def test_returns_chapter_with_paragraphs_and_sentences(self, chapter_repo, neo4j_session):
        neo4j_session.run.return_value = [
            {
                "chapter_id": "ch-1",
                "chapter_title": "Intro",
                "paragraph_id": "p-1",
                "paragraph_index": 0,
                "sentence_id": "s-1",
                "sentence_index": 0,
                "token_id": "t-1",
                "token_index": 0,
                "token_text": "Hello",
                "token_type": "word",
                "token_trailing_ws": " ",
                "token_pos": "NOUN",
                "token_lemma": "hello",
                "token_is_digit": False,
                "token_like_num": False,
                "token_is_alpha": True,
                "token_is_stop": False,
            }
        ]
        ch = chapter_repo.load("ch-1")
        assert ch is not None
        assert ch.id == "ch-1"
        assert ch.title == "Intro"
        assert len(ch.paragraphs) == 1
        assert ch.paragraphs[0].id == "p-1"
        assert len(ch.paragraphs[0].sentences) == 1
        assert ch.paragraphs[0].sentences[0].id == "s-1"
        assert len(ch.paragraphs[0].sentences[0].tokens) == 1
        assert ch.paragraphs[0].sentences[0].tokens[0].text == "Hello"

    def test_defaults_null_title_to_empty(self, chapter_repo, neo4j_session):
        neo4j_session.run.return_value = [
            {
                "chapter_id": "ch-1",
                "chapter_title": None,
                "paragraph_id": None,
                "paragraph_index": None,
                "sentence_id": None,
                "sentence_index": None,
                "token_id": None,
                "token_index": None,
                "token_text": None,
                "token_type": None,
                "token_trailing_ws": None,
                "token_pos": None,
                "token_lemma": None,
                "token_is_digit": None,
                "token_like_num": None,
                "token_is_alpha": None,
                "token_is_stop": None,
            }
        ]
        ch = chapter_repo.load("ch-1")
        assert ch is not None
        assert ch.title == ""
        assert len(ch.paragraphs) == 0

    def test_sets_state_to_sync(self, chapter_repo, neo4j_session):
        neo4j_session.run.return_value = [{"chapter_id": "ch-1", "chapter_title": "X"}]
        ch = chapter_repo.load("ch-1")
        assert ch.state == DataState.SYNC
