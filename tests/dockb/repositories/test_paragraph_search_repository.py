"""Tests for ParagraphSearchRepository — the criteria-matching query."""

from unittest.mock import MagicMock

import pytest
from neo4j import Session

from dockb.repositories.paragraph_search_repository import ParagraphSearchRepository

_OWNER = "acct-1"


@pytest.fixture()
def session():
    mocked = MagicMock(spec=Session)
    mocked.run.return_value = MagicMock()
    return mocked


@pytest.fixture()
def repo(session):
    return ParagraphSearchRepository(session)


def extract_call(mock_session, call_index=0):
    call = mock_session.run.call_args_list[call_index]
    params = call.args[1] if len(call.args) > 1 else call.kwargs
    return call.args[0], params


class TestMatchParagraphs:

    def test_runs_one_query_scoped_to_the_document_and_owner(self, repo, session) -> None:
        session.run.return_value = []

        repo.match_paragraphs("d1", _OWNER, compiled=("true", {}), include_characters=False)

        cypher, params = extract_call(session)
        assert "Document {id: $document_id, owner: $owner}" in cypher
        assert params["document_id"] == "d1"
        assert params["owner"] == _OWNER

    def test_the_where_expression_and_its_params_reach_the_query(self, repo, session) -> None:
        session.run.return_value = []

        repo.match_paragraphs("d1", _OWNER, compiled=("(text =~ $p0)", {"p0": "(?iuU)\\bmurder\\b"}), include_characters=False)

        cypher, params = extract_call(session)
        assert "WHERE (text =~ $p0)" in cypher
        assert params["p0"] == "(?iuU)\\bmurder\\b"

    def test_character_chapters_are_filtered_unless_included(self, repo, session) -> None:
        session.run.return_value = []

        repo.match_paragraphs("d1", _OWNER, compiled=("true", {}), include_characters=False)
        cypher, params = extract_call(session)
        assert "$include_characters" in cypher
        assert "'Character'" in cypher
        assert params["include_characters"] is False

        repo.match_paragraphs("d1", _OWNER, compiled=("true", {}), include_characters=True)
        _, params = extract_call(session, 1)
        assert params["include_characters"] is True

    def test_the_query_reconstructs_text_and_mentions_state_in_the_database(self, repo, session) -> None:
        session.run.return_value = []

        repo.match_paragraphs("d1", _OWNER, compiled=("true", {}), include_characters=False)

        cypher, _ = extract_call(session)
        # tokens concatenated into sentences, sentences joined by newline
        assert "coalesce(t.text" in cypher
        assert 'txt + "\\n"' in cypher
        # the mention verdicts the where-branch reads
        assert "mentions_checked_at" in cypher
        assert ":MENTIONS]" in cypher
        assert "stale" in cypher
        # matches come back in reading order
        assert "ORDER BY chapter_index, index" in cypher

    def test_matches_are_returned_as_plain_dicts(self, repo, session) -> None:
        session.run.return_value = [
            {
                "id": "p1",
                "quote_type": "reading",
                "index": 0,
                "chapter_id": "c1",
                "chapter_title": "Opening 1",
                "chapter_index": 0,
                "sentences": [{"id": "s1", "text": "The murder was discovered."}],
            }
        ]

        rows = repo.match_paragraphs("d1", _OWNER, compiled=("true", {}), include_characters=False)

        assert rows == [
            {
                "id": "p1",
                "quote_type": "reading",
                "index": 0,
                "chapter_id": "c1",
                "chapter_title": "Opening 1",
                "chapter_index": 0,
                "sentences": [{"id": "s1", "text": "The murder was discovered."}],
            }
        ]


class TestDocumentExists:

    def test_true_when_the_owner_owns_the_document(self, repo, session) -> None:
        session.run.return_value = [{"id": "d1"}]

        assert repo.document_exists("d1", _OWNER) is True
        cypher, params = extract_call(session)
        assert "Document {id: $document_id, owner: $owner}" in cypher
        assert params == {"document_id": "d1", "owner": _OWNER}

    def test_false_when_the_document_is_nobodys(self, repo, session) -> None:
        session.run.return_value = []

        assert repo.document_exists("jeremiah", _OWNER) is False


class TestCharacterDirectory:

    def test_lists_the_documents_character_chapters(self, repo, session) -> None:
        session.run.return_value = [{"id": "k1", "title": "Karakas", "first_name": "Karakas", "surname": "Benhur", "nicknames": ["Rak"]}]

        directory = repo.character_directory("d1", _OWNER)

        assert directory == [{"id": "k1", "title": "Karakas", "first_name": "Karakas", "surname": "Benhur", "nicknames": ["Rak"]}]
        cypher, params = extract_call(session)
        assert "Document {id: $document_id, owner: $owner}" in cypher
        assert "'Character'" in cypher
        assert params == {"document_id": "d1", "owner": _OWNER}

    def test_an_empty_directory_comes_back_empty(self, repo, session) -> None:
        session.run.return_value = []

        assert repo.character_directory("d1", _OWNER) == []
