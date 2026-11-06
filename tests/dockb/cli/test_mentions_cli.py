"""The mentions sweep CLI: backfill a document's paragraphs, states 1 and 4 (or all)."""

from unittest.mock import MagicMock

import pytest

from dockb.cli import mentions as cli
from dockb.models.base import DataState
from dockb.models.chapter import Chapter
from dockb.models.document import Document
from dockb.models.paragraph import Paragraph
from dockb.models.sentence import Sentence
from dockb.models.token import POS, Token


@pytest.fixture()
def document():
    document = Document(id="d-uuid-1", title="Linchpin", owner="acct-1", state=DataState.SYNC)
    character = Chapter(id="k1", title="Karakas", category="Character", state=DataState.SYNC)
    character.first_name = "Jeremiah"
    character.surname = "Adams"
    character.nicknames = ["Adams"]
    document.chapters.append(character)
    jael = Chapter(id="k2", title="Jael", category="Character", state=DataState.SYNC)
    jael.first_name = "Jael"
    jael.surname = "Adams"
    document.chapters.append(jael)
    chapter = Chapter(id="c1", title="Opening 1", act="Act I", state=DataState.SYNC)
    paragraph = Paragraph(id="p1", state=DataState.SYNC)
    sentence = Sentence(state=DataState.SYNC)
    sentence.tokens.append(Token(text="Jeremiah", trailing_ws=" ", pos=POS.PROPN, state=DataState.SYNC))
    sentence.tokens.append(Token(text="waited.", trailing_ws="", pos=POS.VERB, state=DataState.SYNC))
    paragraph.sentences.append(sentence)
    chapter.paragraphs.append(paragraph)
    ambiguous = Paragraph(id="p2", state=DataState.SYNC)
    ambiguous_sentence = Sentence(state=DataState.SYNC)
    ambiguous_sentence.tokens.append(Token(text="Adams", trailing_ws=" ", pos=POS.PROPN, state=DataState.SYNC))
    ambiguous_sentence.tokens.append(Token(text="waited.", trailing_ws="", pos=POS.VERB, state=DataState.SYNC))
    ambiguous.sentences.append(ambiguous_sentence)
    chapter.paragraphs.append(ambiguous)
    document.chapters.append(chapter)
    return document


@pytest.fixture()
def wired(document, monkeypatch):
    """The CLI's world: repos over the fixture document, no database touched."""
    chapter_repo = MagicMock()
    chapter_repo.find_document_id.return_value = document.id
    document_repo = MagicMock()
    document_repo.load.return_value = document
    document_repo.list_all.return_value = [{"id": document.id, "title": "Linchpin", "author": "A"}]
    mentions_repo = MagicMock()

    def states(_owner, chapter_id=None, document_id=None):  # pylint: disable=unused-argument
        # the graph's view: p1 settles when tier 1 stamps it; p2's "Adams" is
        # ambiguous and only the model can rule on it
        if chapter_id == "c1" and mentions_repo.stamp.call_args_list:
            return [
                {"id": "p1", "state": 3, "index": 0, "mentions": ["k1"]},
                {"id": "p2", "state": 1, "index": 1, "mentions": []},
            ]
        if chapter_id == "c1":
            return [
                {"id": "p1", "state": 1, "index": 0, "mentions": []},
                {"id": "p2", "state": 1, "index": 1, "mentions": []},
            ]
        return [{"id": "kp1", "state": 2, "index": 0, "mentions": []}]

    mentions_repo.paragraph_states.side_effect = states

    monkeypatch.setattr(cli, "_build", lambda: (chapter_repo, document_repo, mentions_repo))
    monkeypatch.setattr(cli, "account_id_for", lambda _username: "acct-1")
    return chapter_repo, document_repo, mentions_repo


def test_the_sweep_evaluates_the_documents_pending_chapters(wired, capsys):
    _, _, mentions_repo = wired

    code = cli.main(["sweep", "Linchpin", "--owner", "abby"])

    assert code == 0
    mentions_repo.mark_stale.assert_not_called()
    assert mentions_repo.stamp.called
    assert "Opening 1" in capsys.readouterr().out


def test_full_resets_the_verdicts_first(wired):
    _, _, mentions_repo = wired

    code = cli.main(["sweep", "Linchpin", "--owner", "abby", "--full"])

    assert code == 0
    # every chapter is reset: both character chapters and the manuscript chapter
    assert mentions_repo.reset.call_count == 3


def test_the_document_may_be_named_by_its_id(wired):
    _chapter_repo, document_repo, _mentions = wired

    code = cli.main(["sweep", "d-uuid-1", "--owner", "abby"])

    assert code == 0
    document_repo.load.assert_any_call("d-uuid-1", "acct-1")


def test_the_document_may_be_named_by_an_inexactly_cased_title(wired, document, capsys):
    _chapter_repo, document_repo, _mentions = wired
    # the id lookup misses for the raw title; the resolved id loads afterwards
    document_repo.load.side_effect = lambda ref, owner: None if str(ref).lower() == "linchpin" else document

    code = cli.main(["sweep", "LINCHPIN", "--owner", "abby"])

    assert code == 0
    assert "Opening 1" in capsys.readouterr().out


def test_an_unknown_document_fails_with_a_message(wired, capsys):
    _, document_repo, _mentions = wired
    document_repo.load.return_value = None  # the id lookup misses
    document_repo.list_all.return_value = []  # and no title matches

    code = cli.main(["sweep", "Nope", "--owner", "abby"])

    assert code == 1
    assert "Nope" in capsys.readouterr().err


def test_no_ai_is_passed_down_and_a_warning_is_logged(wired, monkeypatch, caplog):  # pylint: disable=too-many-locals
    _, document_repo, mentions_repo = wired
    monkeypatch.setenv("OPENAI_API_KEY", "key-test")
    tier2_kwargs = {}
    real_tier2 = cli.evaluate_chapter_tier2

    # a paragraph whose only evidence is the SHARED surname: a tier-3 candidate
    ambiguous_document = Document(id="d-uuid-1", title="Linchpin", owner="acct-1", state=DataState.SYNC)
    ambiguous_chapter = Chapter(id="c1", title="Opening 1", act="Act I", state=DataState.SYNC)
    ambiguous_paragraph = Paragraph(id="p1", state=DataState.SYNC)
    ambiguous_sentence = Sentence(state=DataState.SYNC)
    ambiguous_sentence.tokens.append(Token(text="Adams", trailing_ws=" ", pos=POS.PROPN, state=DataState.SYNC))
    ambiguous_sentence.tokens.append(Token(text="waited.", trailing_ws="", pos=POS.VERB, state=DataState.SYNC))
    ambiguous_paragraph.sentences.append(ambiguous_sentence)
    ambiguous_chapter.paragraphs.append(ambiguous_paragraph)
    jeremiah = Chapter(id="k1", title="Karakas", category="Character", state=DataState.SYNC)
    jeremiah.first_name = "Jeremiah"
    jeremiah.surname = "Adams"
    jeremiah.nicknames = ["Adams"]
    jael = Chapter(id="k2", title="Jael", category="Character", state=DataState.SYNC)
    jael.first_name = "Jael"
    jael.surname = "Adams"
    for node in (ambiguous_chapter, jeremiah, jael):
        ambiguous_document.chapters.append(node)
    document_repo.load.return_value = ambiguous_document

    def spy(chapter_id, **kwargs):
        tier2_kwargs.update(kwargs)
        return real_tier2(chapter_id, **kwargs)

    monkeypatch.setattr(cli, "evaluate_chapter_tier2", spy)
    mentions_repo.paragraph_states.side_effect = None
    mentions_repo.paragraph_states.return_value = [{"id": "p1", "state": 1, "index": 0, "mentions": []}]

    with caplog.at_level("WARNING"):
        code = cli.main(["sweep", "Linchpin", "--owner", "abby", "--no-ai"])

    assert code == 0
    assert tier2_kwargs.get("no_ai") is True
    assert any("prevented" in record.message for record in caplog.records)


def test_the_sweep_logs_each_mention_and_a_chapter_summary(wired, caplog):
    _chapter_repo, _document_repo, _mentions_repo = wired

    with caplog.at_level("INFO"):
        code = cli.main(["sweep", "Linchpin", "--owner", "abby"])

    assert code == 0
    messages = [record.message for record in caplog.records]
    assert any("Karakas" in m and "Opening 1" in m and "paragraph 0" in m for m in messages)
    assert any("summary" in m.lower() and "Karakas" in m and "Opening 1" in m for m in messages)
