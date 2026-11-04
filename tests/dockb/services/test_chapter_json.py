"""The chapter-as-JSON payload the MCP tools return."""

from unittest.mock import MagicMock

from dockb.models.base import DataState
from dockb.models.chapter import Chapter
from dockb.models.paragraph import Paragraph
from dockb.models.sentence import Sentence
from dockb.models.token import Token
from dockb.services.chapter_json import chapter_payload, load_chapter_payload


def _sentence(*token_texts: str) -> Sentence:
    sentence = Sentence(state=DataState.SYNC)
    for text in token_texts:
        sentence.tokens.append(Token(text=text, trailing_ws=" ", state=DataState.SYNC))
    return sentence


def _chapter() -> Chapter:
    chapter = Chapter(id="c1", title="Opening 1", act="Act I", state=DataState.SYNC)
    quoted = Paragraph(id="p1", quote_type="reading", state=DataState.SYNC)
    quoted.sentences.append(_sentence("Hello", "world."))
    plain = Paragraph(id="p2", state=DataState.SYNC)
    plain.sentences.append(_sentence("Second", "sentence."))
    chapter.paragraphs.append(quoted)
    chapter.paragraphs.append(plain)
    return chapter


def test_paragraphs_carry_their_properties_and_references() -> None:
    payload = chapter_payload(_chapter(), chapter_id_ref="c1", pov_title="Karakas")

    assert payload["id"] == "c1"
    assert payload["title"] == "Opening 1"
    assert payload["act"] == "Act I"
    assert payload["pov"] == "Karakas"
    paragraphs = payload["paragraphs"]
    assert [p["id"] for p in paragraphs] == ["p1", "p2"]
    assert [p["index"] for p in paragraphs] == [0, 1]
    assert all(p["chapter_id"] == "c1" for p in paragraphs)
    assert all(p["chapter_title"] == "Opening 1" for p in paragraphs)
    assert paragraphs[0]["quote_type"] == "reading"
    assert paragraphs[1]["quote_type"] == ""


def test_sentences_carry_their_properties_and_canonical_text() -> None:
    payload = chapter_payload(_chapter(), chapter_id_ref="c1", pov_title=None)

    first = payload["paragraphs"][0]["sentences"]
    assert [s["text"] for s in first] == ["Hello world."]
    assert [s["index"] for s in first] == [0]
    assert all(s["id"] for s in first)
    second = payload["paragraphs"][1]["sentences"]
    assert [s["text"] for s in second] == ["Second sentence."]
    assert second[0]["index"] == 0


def test_sentence_text_strips_the_trailing_whitespace_of_the_last_token() -> None:
    chapter = Chapter(id="c1", state=DataState.SYNC)
    paragraph = Paragraph(id="p1", state=DataState.SYNC)
    sentence = Sentence(state=DataState.SYNC)
    sentence.tokens.append(Token(text="End.", trailing_ws=" ", state=DataState.SYNC))
    paragraph.sentences.append(sentence)
    chapter.paragraphs.append(paragraph)

    payload = chapter_payload(chapter, chapter_id_ref="c1", pov_title=None)

    assert payload["paragraphs"][0]["sentences"][0]["text"] == "End."


def test_load_chapter_payload_loads_and_resolves_the_pov_title() -> None:
    chapter = Chapter(id="c1", title="Opening 1", pov="k1", state=DataState.SYNC)
    repo = MagicMock()
    repo.load.return_value = chapter
    repo.find_document_id.return_value = "d1"
    repo.find_character_title.return_value = "Karakas"

    payload = load_chapter_payload("c1", chapter_repo=repo, owner="acct-1")

    assert payload is not None
    assert payload["id"] == "c1"
    assert payload["pov"] == "Karakas"


def test_load_chapter_payload_of_an_unknown_chapter_is_none() -> None:
    repo = MagicMock()
    repo.load.return_value = None

    assert load_chapter_payload("nope", chapter_repo=repo, owner="acct-1") is None
