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
