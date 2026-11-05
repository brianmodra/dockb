"""Tier 1 of the mention pipeline: the deterministic name-set evaluation."""

from unittest.mock import MagicMock

from dockb.models.base import DataState
from dockb.models.chapter import Chapter
from dockb.models.document import Document
from dockb.models.paragraph import Paragraph
from dockb.models.sentence import Sentence
from dockb.models.token import POS, Token
from dockb.services.mentions import evaluate_chapter_tier1

_OWNER = "acct-1"


def _paragraph(par_id: str, words_and_pos: list[tuple[str, POS]]) -> Paragraph:
    paragraph = Paragraph(id=par_id, state=DataState.SYNC)
    sentence = Sentence(state=DataState.SYNC)
    for text, pos in words_and_pos:
        sentence.tokens.append(Token(text=text, trailing_ws=" ", pos=pos, state=DataState.SYNC))
    paragraph.sentences.append(sentence)
    return paragraph


def _character(chapter_id: str, title: str, **props) -> Chapter:
    character = Chapter(id=chapter_id, title=title, category="Character", state=DataState.SYNC)
    character.first_name = props.get("first_name", "")
    character.surname = props.get("surname", "")
    character.middle_names = list(props.get("middle_names", []))
    character.nicknames = list(props.get("nicknames", []))
    return character


def _document() -> Document:
    document = Document(id="d1", state=DataState.SYNC)
    chapter = Chapter(id="c1", title="Opening 1", state=DataState.SYNC)
    chapter.paragraphs.append(_paragraph("p1", [("The", POS.DET), ("murder", POS.NOUN), ("was", POS.AUX), ("discovered", POS.VERB)]))
    chapter.paragraphs.append(_paragraph("p2", [("Jeremiah", POS.PROPN), ("spoke", POS.VERB)]))
    chapter.paragraphs.append(_paragraph("p3", [("Adams", POS.PROPN), ("entered", POS.VERB)]))
    chapter.paragraphs.append(_paragraph("p4", [("Jer-bear", POS.PROPN), ("smiled", POS.VERB)]))
    document.chapters.append(chapter)
    return document


def _fixture(chapter_states: list[dict]):
    document = _document()
    jeremiah = _character(
        "k1",
        "Jeremiah",
        first_name="Jeremiah",
        surname="Adams",
        middle_names=["Edgar"],
        nicknames=["Adams", "Jer", "Jer-bear"],
    )
    jael = _character("k2", "Jael", first_name="Jael", surname="Adams")
    document.chapters.append(jeremiah)
    document.chapters.append(jael)

    mentions_repo = MagicMock()
    mentions_repo.paragraph_states.return_value = chapter_states
    chapter_repo = MagicMock()
    chapter_repo.load.return_value = next(c for c in document.chapters if c.id == "c1")
    chapter_repo.find_document_id.return_value = "d1"
    document_repo = MagicMock()
    document_repo.load.return_value = document
    return mentions_repo, chapter_repo, document_repo, jeremiah


def test_a_first_name_match_becomes_a_name_verdict() -> None:
    mentions_repo, chapter_repo, document_repo, _jeremiah = _fixture([{"id": "p2", "state": 1}])

    evaluate_chapter_tier1(
        "c1",
        owner=_OWNER,
        mentions_repo=mentions_repo,
        chapter_repo=chapter_repo,
        document_repo=document_repo,
    )

    stamped = mentions_repo.stamp.call_args
    assert stamped is not None
    assert stamped.args[0] == "p2"
    assert stamped.kwargs["checked_at"]
    assert stamped.args[1] == [{"character_id": "k1", "method": "name", "confidence": 1.0}]


def test_an_ambiguous_name_is_left_pending_not_stamped() -> None:
    # "Adams" is Jeremiah's nickname AND Jael's surname: tier 1 may not judge it.
    mentions_repo, chapter_repo, document_repo, _jeremiah = _fixture([{"id": "p3", "state": 1}])

    evaluate_chapter_tier1(
        "c1",
        owner=_OWNER,
        mentions_repo=mentions_repo,
        chapter_repo=chapter_repo,
        document_repo=document_repo,
    )

    mentions_repo.stamp.assert_not_called()


def test_a_hyphenated_nickname_matches_through_its_tokens() -> None:
    # "Jer-bear" is split by spaCy into Jer - bear; the joined text still names him.
    mentions_repo, chapter_repo, document_repo, _jeremiah = _fixture([{"id": "p4", "state": 1}])

    evaluate_chapter_tier1(
        "c1",
        owner=_OWNER,
        mentions_repo=mentions_repo,
        chapter_repo=chapter_repo,
        document_repo=document_repo,
    )

    stamped = mentions_repo.stamp.call_args
    assert stamped is not None and stamped.args[0] == "p4"
    assert [v["character_id"] for v in stamped.args[1]] == ["k1"]


def test_a_paragraph_with_no_name_tokens_becomes_state_2() -> None:
    mentions_repo, chapter_repo, document_repo, _jeremiah = _fixture([{"id": "p1", "state": 1}])

    evaluate_chapter_tier1(
        "c1",
        owner=_OWNER,
        mentions_repo=mentions_repo,
        chapter_repo=chapter_repo,
        document_repo=document_repo,
    )

    stamped = mentions_repo.stamp.call_args
    assert stamped is not None
    assert stamped.args[0] == "p1"
    assert stamped.args[1] == []


def test_states_2_and_3_paragraphs_are_not_touched() -> None:
    mentions_repo, chapter_repo, document_repo, _jeremiah = _fixture(
        [
            {"id": "p2", "state": 1},
            {"id": "p3", "state": 2},
            {"id": "p1", "state": 3},
            {"id": "p4", "state": 4},
        ]
    )

    evaluate_chapter_tier1(
        "c1",
        owner=_OWNER,
        mentions_repo=mentions_repo,
        chapter_repo=chapter_repo,
        document_repo=document_repo,
    )

    stamped_ids = [call.args[0] for call in mentions_repo.stamp.call_args_list]
    assert sorted(stamped_ids) == ["p2", "p4"]
