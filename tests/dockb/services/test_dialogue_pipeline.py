"""Tests for the save-time dialogue pipeline."""

from __future__ import annotations

from unittest.mock import MagicMock

from dockb.models.chapter import Chapter
from dockb.models.paragraph import Paragraph
from dockb.models.sentence import Sentence
from dockb.models.token import POS, Token
from dockb.services import dialogue_pipeline
from dockb.services.dialogue import CLOSING_QUOTE, OPENING_QUOTE

_OWNER = "acct-1"
_DOC = "d-1"
_CHAPTER = "ch-1"


def _token(token_id: str, text: str, pos: POS, trailing_ws: str = " ", lemma: str = "") -> Token:
    return Token(id=token_id, text=text, pos=pos, trailing_ws=trailing_ws, lemma=lemma or text.lower())


def _dialogue_sentence() -> Sentence:
    return Sentence(
        id="s-1",
        tokens=[
            _token("t-0", '"', POS.PUNCT, trailing_ws=""),
            _token("t-1", "Hello", POS.INTJ, trailing_ws=""),
            _token("t-2", ",", POS.PUNCT, trailing_ws=""),
            _token("t-3", '"', POS.PUNCT, trailing_ws=" "),
            _token("t-4", "Mary", POS.PROPN),
            _token("t-5", "said", POS.VERB, trailing_ws="", lemma="say"),
            _token("t-6", ".", POS.PUNCT, trailing_ws=""),
        ],
    )


def _chapter(sentence: Sentence) -> Chapter:
    return Chapter(id=_CHAPTER, title="Opening", paragraphs=[Paragraph(sentences=[sentence])])


def _characters() -> list[Chapter]:
    return [Chapter(id="c-1", category="Character", title="Mary", first_name="Mary")]


def _repos(sentence: Sentence, characters: list[Chapter] | None = None, *, name_found: bool = True):
    chapter_repo = MagicMock()
    chapter_repo.find_document_id.return_value = _DOC
    chapter_repo.load.return_value = _chapter(sentence)
    chapter_repo.list_characters.return_value = characters if characters is not None else _characters()
    chapter_repo.find_character_by_name.return_value = {"id": "c-1", "title": "Mary"} if name_found else None
    sentence_repo = MagicMock()
    return chapter_repo, sentence_repo


def test_the_pipeline_stamps_dialogue_quote_fixes_and_the_speaker() -> None:
    sentence = _dialogue_sentence()
    chapter_repo, sentence_repo = _repos(sentence)

    dialogue_pipeline.evaluate_chapter_dialogue(_CHAPTER, owner=_OWNER, chapter_repo=chapter_repo, sentence_repo=sentence_repo)

    chapter_repo.find_document_id.assert_called_once_with(_CHAPTER, _OWNER)
    chapter_repo.list_characters.assert_called_once_with(_DOC, _OWNER)

    stamps = sentence_repo.stamp_dialogue.call_args.args[0]
    assert len(stamps) == 1
    stamp = stamps[0]
    assert stamp["sentence_id"] == "s-1"
    assert stamp["is_dialogue"] is True
    assert stamp["start_token"] == 1
    assert stamp["end_token"] == 2
    assert stamp["spans"] == [(1, 2)]
    assert stamp["checked_at"]
    assert stamp["tokens"] == [
        {"id": "t-0", "text": OPENING_QUOTE, "trailing_ws": ""},
        {"id": "t-3", "text": CLOSING_QUOTE, "trailing_ws": " "},
    ]
    assert sentence_repo.stamp_dialogue.call_args.kwargs == {"owner": _OWNER}

    rows = sentence_repo.stamp_spoken_by.call_args.args[0]
    assert rows == [
        {
            "sentence_id": "s-1",
            "character_id": "c-1",
            "method": "name",
            "confidence": 1.0,
            "reference": "Mary",
            "stale": False,
        }
    ]
    assert sentence_repo.stamp_spoken_by.call_args.kwargs == {"owner": _OWNER}


def test_the_pipeline_keeps_an_unresolved_reference_on_the_edge() -> None:
    sentence = _dialogue_sentence()
    chapter_repo, sentence_repo = _repos(sentence, characters=[], name_found=False)

    dialogue_pipeline.evaluate_chapter_dialogue(_CHAPTER, owner=_OWNER, chapter_repo=chapter_repo, sentence_repo=sentence_repo)

    rows = sentence_repo.stamp_spoken_by.call_args.args[0]
    assert rows[0]["character_id"] == "unresolved"
    assert rows[0]["method"] == "unresolved"
    assert rows[0]["reference"] == "Mary"


def test_the_pipeline_skips_sentences_already_checked() -> None:
    sentence = _dialogue_sentence()
    sentence.dialogue_checked_at = "2026-01-02T03:04:05+00:00"
    chapter_repo, sentence_repo = _repos(sentence)

    dialogue_pipeline.evaluate_chapter_dialogue(_CHAPTER, owner=_OWNER, chapter_repo=chapter_repo, sentence_repo=sentence_repo)

    sentence_repo.stamp_dialogue.assert_not_called()
    sentence_repo.stamp_spoken_by.assert_not_called()
