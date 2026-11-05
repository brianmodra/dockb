"""The MCP find_paragraphs criteria tree and chapter lookups."""

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


def _search_service(document: Document):
    chapter_repo = MagicMock()
    chapter_repo.load.return_value = document.chapters[0]
    chapter_repo.find_document_id.return_value = "d1"
    chapter_repo.find_character_title.return_value = None
    document_repo = MagicMock()
    document_repo.load.return_value = document
    return chapter_repo, document_repo


def test_find_paragraphs_returns_payloads_with_chapter_and_position() -> None:
    document = _document()
    chapter_repo, document_repo = _search_service(document)

    found = find_paragraphs_payload(
        "d1",
        {"type": "word", "word": "murder"},
        chapter_repo=chapter_repo,
        document_repo=document_repo,
        owner="acct-1",
    )

    assert len(found) == 1
    assert found[0]["chapter_id"] == "c1"
    assert found[0]["chapter_title"] == "Opening 1"
    assert found[0]["index"] == 0
    assert found[0]["id"] == "p1"
    assert found[0]["sentences"][0]["text"] == "The murder was discovered at dawn."


def test_find_paragraphs_resolves_a_character_by_name_for_the_match() -> None:
    document = _document()
    character = Chapter(id="k1", title="Karakas", category="Character", state=DataState.SYNC)
    character.first_name = "Kiral"
    character.surname = "Karakas"
    character.nicknames = ["Adams"]
    document.chapters.append(character)
    chapter_repo, document_repo = _search_service(document)
    chapter_repo.find_character_by_name.return_value = {"id": "k1", "title": "Karakas"}

    found = find_paragraphs_payload(
        "d1",
        {"type": "character", "character": "Kiral"},
        chapter_repo=chapter_repo,
        document_repo=document_repo,
        owner="acct-1",
    )

    assert [p["id"] for p in found] == ["p2"]


def test_find_paragraphs_excludes_character_chapters_unless_asked() -> None:
    document = _document()
    character = Chapter(id="k1", title="Karakas", category="Character", state=DataState.SYNC)
    character.paragraphs.append(_paragraph("kp1", "The murder room."))
    document.chapters.append(character)
    chapter_repo, document_repo = _search_service(document)
    criteria = {"type": "word", "word": "murder"}

    default_run = find_paragraphs_payload("d1", criteria, chapter_repo=chapter_repo, document_repo=document_repo, owner="acct-1")
    with_characters = find_paragraphs_payload(
        "d1",
        criteria,
        chapter_repo=chapter_repo,
        document_repo=document_repo,
        owner="acct-1",
        include_characters=True,
    )

    assert [p["id"] for p in default_run] == ["p1"]
    assert [(p["id"], p["chapter_id"]) for p in with_characters] == [("p1", "c1"), ("kp1", "k1")]


def test_find_paragraphs_answers_evaluated_paragraphs_from_the_cache() -> None:
    document = _document()  # p1: "The murder was discovered at dawn." (no names in text)
    character = Chapter(id="k1", title="Karakas", category="Character", state=DataState.SYNC)
    document.chapters.append(character)
    chapter_repo, document_repo = _search_service(document)
    mentions_repo = MagicMock()
    mentions_repo.paragraph_states.return_value = [
        {"id": "p1", "state": 3, "mentions": ["k1"]},  # the cache says: a mention of k1
        {"id": "p2", "state": 2, "mentions": []},  # evaluated: mentions nobody
        {"id": "p3", "state": 1, "mentions": []},  # never evaluated
    ]

    found = find_paragraphs_payload(
        "d1",
        {"type": "character", "character": "k1"},
        chapter_repo=chapter_repo,
        document_repo=document_repo,
        owner="acct-1",
        mentions_repo=mentions_repo,
    )

    # state 3 answered from the cache; state 2 stayed out despite its text
    assert [p["id"] for p in found] == ["p1"]


def test_find_paragraphs_enqueues_the_evaluation_of_the_un_evaluated() -> None:
    from dockb.services import mcp_queries

    document = _document()
    chapter_repo, document_repo = _search_service(document)
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
        chapter_repo=chapter_repo,
        document_repo=document_repo,
        owner="acct-1",
        mentions_repo=mentions_repo,
    )

    mcp_queries.run_mentions_async = original
    assert len(enqueued) == 1  # the document-wide evaluation is queued
    assert not found  # no names in these paragraphs' texts: nothing inline matched


def test_find_paragraphs_of_an_unowned_document_is_empty() -> None:
    document = _document()
    chapter_repo, document_repo = _search_service(document)
    document_repo.load.return_value = None

    found = find_paragraphs_payload(
        "d1",
        {"type": "word", "word": "murder"},
        chapter_repo=chapter_repo,
        document_repo=document_repo,
        owner="other",
    )
    assert not found
