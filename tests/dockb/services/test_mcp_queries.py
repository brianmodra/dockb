"""The MCP find_paragraphs criteria tree and chapter lookups."""

from typing import Any
from unittest.mock import MagicMock

from dockb.models.base import DataState
from dockb.models.chapter import Chapter
from dockb.models.document import Document
from dockb.models.paragraph import Paragraph
from dockb.models.sentence import Sentence
from dockb.models.token import Token
from dockb.services.mcp_queries import evaluate_criteria, find_paragraphs_payload


def _token(text: str) -> Token:
    return Token(text=text, trailing_ws=" ", state=DataState.SYNC)


def _paragraph(par_id: str, text: str, quote_type: str = "") -> Paragraph:
    paragraph = Paragraph(id=par_id, quote_type=quote_type, state=DataState.SYNC)
    sentence = Sentence(state=DataState.SYNC)
    for word in text.split():
        sentence.tokens.append(_token(word))
    paragraph.sentences.append(sentence)
    return paragraph


def _document() -> Document:
    document = Document(id="d1", state=DataState.SYNC)
    chapter = Chapter(id="c1", title="Opening 1", state=DataState.SYNC)
    chapter.paragraphs.append(_paragraph("p1", "The murder was discovered at dawn."))
    chapter.paragraphs.append(_paragraph("p2", "Kiral inspected the study.", quote_type="reading"))
    chapter.paragraphs.append(_paragraph("p3", "Nothing else moved."))
    document.chapters.append(chapter)
    return document


# -- leaves ---------------------------------------------------------------


def test_a_word_leaf_matches_whole_words_only() -> None:
    text = "The murder was discovered."
    assert evaluate_criteria({"type": "word", "word": "murder"}, text) is True
    assert evaluate_criteria({"type": "word", "word": "murderer"}, text) is False
    assert evaluate_criteria({"type": "word", "word": "MURDER"}, text) is True


def test_a_text_leaf_matches_a_substring_case_insensitively() -> None:
    text = "The murder was discovered at dawn."
    assert evaluate_criteria({"type": "text", "text": "discovered at"}, text) is True
    assert evaluate_criteria({"type": "text", "text": "DISCOVERED"}, text) is True
    assert evaluate_criteria({"type": "text", "text": "buried"}, text) is False


def test_a_character_leaf_matches_first_name_nickname_or_first_and_surname() -> None:
    names = ["Kiral", "Adams", "Kiral Karakas"]  # first name, nickname, first+surname
    assert evaluate_criteria({"type": "character", "character": "k1"}, text="Karakas inspected.", names=names) is False
    assert evaluate_criteria({"type": "character", "character": "k1"}, text="Adams inspected.", names=names) is True
    assert evaluate_criteria({"type": "character", "character": "k1"}, text="Kiral Karakas inspected.", names=names) is True
    assert evaluate_criteria({"type": "character", "character": "k1"}, text="Kiralah inspected.", names=names) is False


# -- operators ------------------------------------------------------------


def test_an_and_node_requires_every_child_to_match() -> None:
    criteria = {
        "type": "criteria",
        "op": "and",
        "criteria": [
            {"type": "word", "word": "murder"},
            {"type": "text", "text": "dawn"},
        ],
    }
    assert evaluate_criteria(criteria, "The murder at dawn.") is True
    assert evaluate_criteria(criteria, "The murder at dusk.") is False


def test_an_or_node_needs_any_child_to_match() -> None:
    criteria = {
        "type": "criteria",
        "op": "or",
        "criteria": [
            {"type": "word", "word": "murder"},
            {"type": "text", "text": "dusk"},
        ],
    }
    assert evaluate_criteria(criteria, "The murder at dawn.") is True
    assert evaluate_criteria(criteria, "Quiet dusk.") is True
    assert evaluate_criteria(criteria, "Quiet dawn.") is False


def test_the_nested_example_from_the_contract() -> None:
    criteria = {
        "type": "criteria",
        "op": "and",
        "criteria": [
            {"type": "word", "word": "murder"},
            {
                "type": "criteria",
                "op": "or",
                "criteria": [
                    {"type": "character", "character": "Karakas"},
                    {"type": "character", "character": "Arthurton"},
                ],
            },
        ],
    }
    assert evaluate_criteria(criteria, "The murder: Karakas inspected.", names=["Karakas"]) is True
    assert evaluate_criteria(criteria, "The murder: Arthurton inspected.", names=["Arthurton"]) is True
    assert evaluate_criteria(criteria, "The murder: nobody inspected.") is False
    assert evaluate_criteria(criteria, "Karakas inspected.", names=["Karakas"]) is False


# -- the document-level search --------------------------------------------


class _StubSearchRepo:
    """The search repository: rows to return, and the calls they answered."""

    def __init__(
        self,
        rows: list[dict[str, object]] | None = None,
        directory: list[dict[str, object]] | None = None,
        exists: bool = True,
    ) -> None:
        self.rows = rows if rows is not None else []
        self.directory = directory or []
        self.exists = exists
        self.calls: list[dict[str, Any]] = []

    def document_exists(self, document_id: str, owner: str) -> bool:  # pylint: disable=unused-argument
        return self.exists

    def character_directory(self, document_id: str, owner: str) -> list[dict[str, object]]:  # pylint: disable=unused-argument
        return self.directory

    def match_paragraphs(
        self,
        document_id: str,
        owner: str,
        *,
        compiled: tuple[str, dict[str, Any]],
        include_characters: bool,
    ) -> list[dict[str, object]]:
        self.calls.append(
            {
                "document_id": document_id,
                "owner": owner,
                "where": compiled[0],
                "params": compiled[1],
                "include_characters": include_characters,
            }
        )
        return self.rows


_ROW = {
    "id": "p1",
    "quote_type": "reading",
    "index": 0,
    "chapter_id": "c1",
    "chapter_title": "Opening 1",
    "chapter_index": 0,
    "sentences": [{"id": "s1", "text": "The murder was discovered at dawn."}],
}


def test_find_paragraphs_returns_the_querys_rows_as_payloads() -> None:
    search_repo = _StubSearchRepo(rows=[_ROW])
    chapter_repo = MagicMock()

    found = find_paragraphs_payload(
        "d1",
        {"type": "word", "word": "murder"},
        search_repo=search_repo,
        chapter_repo=chapter_repo,
        document_repo=MagicMock(),
        owner="acct-1",
    )

    assert len(found) == 1
    assert found[0]["id"] == "p1"
    assert found[0]["chapter_id"] == "c1"
    assert found[0]["chapter_title"] == "Opening 1"
    assert found[0]["index"] == 0
    assert found[0]["quote_type"] == "reading"
    assert found[0]["sentences"] == [{"id": "s1", "index": 0, "text": "The murder was discovered at dawn."}]
    # the search's own sentence is marked, so the model can name it in a button
    assert found[0]["matched_sentence_ids"] == ["s1"]
    # the criteria reached the database compiled: a whole-word regex parameter
    assert search_repo.calls == [
        {
            "document_id": "d1",
            "owner": "acct-1",
            "where": "(text =~ $p0)",
            "params": {"p0": "(?isuU).*\\bmurder\\b.*"},
            "include_characters": False,
        }
    ]


def test_find_paragraphs_marks_every_sentence_the_criteria_selects() -> None:
    multi = {
        "id": "p2",
        "quote_type": "",
        "index": 1,
        "chapter_id": "c1",
        "chapter_title": "Opening 1",
        "sentences": [
            {"id": "s1", "text": "Karakas closed the door."},
            {"id": "s2", "text": "The murder was discovered at dawn."},
            {"id": "s3", "text": "Jael laughed last month."},
        ],
    }

    found = find_paragraphs_payload(
        "d1",
        {
            "type": "criteria",
            "op": "or",
            "criteria": [
                {"type": "word", "word": "Karakas"},
                {"type": "word", "word": "murder"},
            ],
        },
        search_repo=_StubSearchRepo(rows=[multi]),
        chapter_repo=MagicMock(),
        document_repo=MagicMock(),
        owner="acct-1",
    )
    assert found[0]["matched_sentence_ids"] == ["s1", "s2"]

    def found_with(*args: Any, **kwargs: Any) -> Any:
        kwargs["search_repo"] = _StubSearchRepo(rows=[multi])
        return find_paragraphs_payload(*args, **kwargs)

    found = found_with(
        "d1",
        {
            "type": "criteria",
            "op": "and",
            "criteria": [
                {"type": "word", "word": "Karakas"},
                {"type": "word", "word": "murder"},
            ],
        },
        chapter_repo=MagicMock(),
        document_repo=MagicMock(),
        owner="acct-1",
    )
    # the two words live in different sentences here: nothing is marked, and the
    # model then names no sentences, highlighting the whole paragraph
    assert found[0]["matched_sentence_ids"] == []


def test_find_paragraphs_marks_a_sentence_whose_text_leaf_is_a_substring() -> None:
    multi = {
        "id": "p2",
        "quote_type": "",
        "index": 1,
        "chapter_id": "c1",
        "chapter_title": "Opening 1",
        "sentences": [
            {"id": "s1", "text": "Something was Discovered in the dark."},
            {"id": "s2", "text": "It rained."},
        ],
    }
    found = find_paragraphs_payload(
        "d1",
        {"type": "text", "text": "was discovered"},
        search_repo=_StubSearchRepo(rows=[multi]),
        chapter_repo=MagicMock(),
        document_repo=MagicMock(),
        owner="acct-1",
    )
    assert found[0]["matched_sentence_ids"] == ["s1"]


def test_find_paragraphs_marks_sentences_by_the_characters_it_resolves() -> None:
    multi = {
        "id": "p2",
        "quote_type": "",
        "index": 1,
        "chapter_id": "c1",
        "chapter_title": "Opening 1",
        "sentences": [
            {"id": "s1", "text": "Karakas closed the door."},
            {"id": "s2", "text": "Nobody was at home."},
        ],
    }
    search_repo = _StubSearchRepo(
        directory=[{"id": "k1", "title": "Karakas", "first_name": "Kiral", "surname": "Karakas", "nicknames": []}],
        rows=[multi],
    )
    found = find_paragraphs_payload(
        "d1",
        {"type": "character", "character": "Karakas"},
        search_repo=search_repo,
        chapter_repo=MagicMock(),
        document_repo=MagicMock(),
        owner="acct-1",
    )
    assert search_repo.character_directory(document_id="d1", owner="acct-1")  # the directory is a stub
    assert found[0]["matched_sentence_ids"] == ["s1"]


def test_sentence_marking_runs_every_lookup_before_the_mentions_job_starts(monkeypatch) -> None:
    """The mentions job runs on a daemon thread sharing the tool's session.

    The sentence marker asks the database while it marks, so it must finish
    before the job is spawned: two threads running one session corrupts the
    driver's connection (a BufferError in the wild).
    """
    from dockb.services import mcp_queries as module

    events: list[str] = []
    chapter_repo = MagicMock()

    def noting(*args: Any, **kwargs: Any) -> dict[str, str]:
        events.append("resolve")
        return {"id": "k1", "title": "Karakas"}

    chapter_repo.find_character_by_name.side_effect = noting
    monkeypatch.setattr(module, "run_mentions_async", lambda job: events.append("job"))
    search_repo = _StubSearchRepo(
        directory=[{"id": "k1", "title": "Karakas", "first_name": "K", "surname": "Karakas", "nicknames": ["Adams"]}],
        rows=[
            {
                "id": "p1",
                "quote_type": "",
                "index": 0,
                "chapter_id": "c1",
                "chapter_title": "Opening 1",
                "sentences": [{"id": "s1", "text": "Adams closed the door."}],
            }
        ],
    )
    mentions_repo = MagicMock()
    mentions_repo.paragraph_states.return_value = [{"id": "p1", "state": 1}]

    find_paragraphs_payload(
        "d1",
        {"type": "character", "character": "Adams"},
        search_repo=search_repo,
        chapter_repo=chapter_repo,
        document_repo=MagicMock(),
        owner="acct-1",
        mentions_repo=mentions_repo,
    )

    assert "resolve" in events
    assert events[-1] == "job"
    assert all(event == "resolve" for event in events[:-1])


def test_find_paragraphs_refuses_an_unknown_document_before_searching() -> None:
    search_repo = _StubSearchRepo(exists=False)

    found = find_paragraphs_payload(
        "jeremiah",
        {"type": "word", "word": "murder"},
        search_repo=search_repo,
        chapter_repo=MagicMock(),
        document_repo=MagicMock(),
        owner="acct-1",
    )

    assert found is None
    assert not search_repo.calls  # no search runs against a document nobody owns


def test_find_paragraphs_excludes_character_chapters_unless_asked() -> None:
    search_repo = _StubSearchRepo()

    find_paragraphs_payload(
        "d1",
        {"type": "word", "word": "murder"},
        search_repo=search_repo,
        chapter_repo=MagicMock(),
        document_repo=MagicMock(),
        owner="acct-1",
    )
    find_paragraphs_payload(
        "d1",
        {"type": "word", "word": "murder"},
        search_repo=search_repo,
        chapter_repo=MagicMock(),
        document_repo=MagicMock(),
        owner="acct-1",
        include_characters=True,
    )

    assert [call["include_characters"] for call in search_repo.calls] == [False, True]


def test_find_paragraphs_resolves_a_character_through_the_directory() -> None:
    search_repo = _StubSearchRepo(
        directory=[{"id": "k1", "title": "Karakas", "first_name": "Kiral", "surname": "Karakas", "nicknames": ["Adams"]}]
    )
    chapter_repo = MagicMock()
    chapter_repo.find_character_by_name.return_value = {"id": "k1", "title": "Karakas"}

    find_paragraphs_payload(
        "d1",
        {"type": "character", "character": "Kiral"},
        search_repo=search_repo,
        chapter_repo=chapter_repo,
        document_repo=MagicMock(),
        owner="acct-1",
    )

    # the given name matched no directory row, so the name search resolved it
    chapter_repo.find_character_by_name.assert_called_once_with("d1", ["Kiral"], "acct-1")
    call = search_repo.calls[0]
    assert call["params"]["p0"] == "k1"
    assert call["params"]["p1"] == [
        "(?isuU).*\\bKiral\\b.*",
        "(?isuU).*\\bKiral\\ Karakas\\b.*",
        "(?isuU).*\\bAdams\\b.*",
    ]


def test_find_paragraphs_resolves_a_character_by_title_without_a_name_search() -> None:
    search_repo = _StubSearchRepo(directory=[{"id": "k1", "title": "Karakas", "first_name": "Karakas", "surname": "", "nicknames": []}])
    chapter_repo = MagicMock()

    find_paragraphs_payload(
        "d1",
        {"type": "character", "character": "karakas"},
        search_repo=search_repo,
        chapter_repo=chapter_repo,
        document_repo=MagicMock(),
        owner="acct-1",
    )

    chapter_repo.find_character_by_name.assert_not_called()
    assert search_repo.calls[0]["params"]["p0"] == "k1"


def test_find_paragraphs_compiles_the_cache_branch_for_a_resolved_character() -> None:
    """The compiled leaf reads the mentions cache first, inline names second."""
    search_repo = _StubSearchRepo(directory=[{"id": "k1", "title": "Karakas", "first_name": "Karakas", "surname": "", "nicknames": []}])
    mentions_repo = MagicMock()
    mentions_repo.paragraph_states.return_value = [
        {"id": "p1", "state": 3, "mentions": ["k1"]},  # the cache says: a mention of k1
        {"id": "p2", "state": 2, "mentions": []},  # evaluated: mentions nobody
    ]

    find_paragraphs_payload(
        "d1",
        {"type": "character", "character": "Karakas"},
        search_repo=search_repo,
        chapter_repo=MagicMock(),
        document_repo=MagicMock(),
        owner="acct-1",
        mentions_repo=mentions_repo,
    )

    assert "checked IS NOT NULL AND NOT hasStale AND $p0 IN valid" in search_repo.calls[0]["where"]
    assert "any(n IN $p1 WHERE text =~ n)" in search_repo.calls[0]["where"]


def test_find_paragraphs_enqueues_the_evaluation_of_the_un_evaluated() -> None:
    from dockb.services import mcp_queries

    search_repo = _StubSearchRepo()
    mentions_repo = MagicMock()
    mentions_repo.paragraph_states.return_value = [
        {"id": "p1", "state": 1, "mentions": []},
        {"id": "p2", "state": 4, "mentions": []},
    ]
    enqueued = []
    original = mcp_queries.run_mentions_async
    mcp_queries.run_mentions_async = enqueued.append

    found = find_paragraphs_payload(
        "d1",
        {"type": "character", "character": "Karakas"},
        search_repo=search_repo,
        chapter_repo=MagicMock(),
        document_repo=MagicMock(),
        owner="acct-1",
        mentions_repo=mentions_repo,
    )

    mcp_queries.run_mentions_async = original
    assert len(enqueued) == 1  # the document-wide evaluation is queued
    assert found == []  # nothing matched: the search itself never waits on the model


def test_find_paragraphs_enqueues_nothing_for_a_word_only_search() -> None:
    from dockb.services import mcp_queries

    search_repo = _StubSearchRepo()
    mentions_repo = MagicMock()
    mentions_repo.paragraph_states.return_value = [{"id": "p1", "state": 1, "mentions": []}]
    enqueued = []
    original = mcp_queries.run_mentions_async
    mcp_queries.run_mentions_async = enqueued.append

    find_paragraphs_payload(
        "d1",
        {"type": "word", "word": "murder"},
        search_repo=search_repo,
        chapter_repo=MagicMock(),
        document_repo=MagicMock(),
        owner="acct-1",
        mentions_repo=mentions_repo,
    )

    mcp_queries.run_mentions_async = original
    assert not enqueued  # word leaves read no mentions cache, so none is refreshed


def test_find_paragraphs_of_an_unowned_document_is_none() -> None:
    """An unknown or other-account document is None — distinct from no matches."""
    search_repo = _StubSearchRepo(exists=False)

    found = find_paragraphs_payload(
        "d1",
        {"type": "word", "word": "murder"},
        search_repo=search_repo,
        chapter_repo=MagicMock(),
        document_repo=MagicMock(),
        owner="other",
    )
    assert found is None
