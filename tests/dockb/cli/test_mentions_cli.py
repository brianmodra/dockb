"""The mentions sweep CLI: backfill a document's paragraphs, states 1 and 4 (or all)."""

from unittest.mock import MagicMock

import pytest

from dockb.cli import mentions as cli
from dockb.models.base import DataState
from dockb.models.chapter import Chapter
from dockb.models.document import Document
from dockb.models.paragraph import Paragraph
from dockb.models.sentence import Sentence
from dockb.models.token import Token


@pytest.fixture()
def document():
    document = Document(id="d-uuid-1", title="Linchpin", owner="acct-1", state=DataState.SYNC)
    character = Chapter(id="k1", title="Karakas", category="Character", state=DataState.SYNC)
    document.chapters.append(character)
    chapter = Chapter(id="c1", title="Opening 1", act="Act I", state=DataState.SYNC)
    paragraph = Paragraph(id="p1", state=DataState.SYNC)
    sentence = Sentence(state=DataState.SYNC)
    sentence.tokens.append(Token(text="Body.", trailing_ws=" ", state=DataState.SYNC))
    paragraph.sentences.append(sentence)
    chapter.paragraphs.append(paragraph)
    document.chapters.append(chapter)
    return document


def account_id_for(_username: str) -> str:
    return "acct-1"


@pytest.fixture()
def wired(document, monkeypatch):
    """The CLI's world: repos over the fixture document, no database touched."""
    chapter_repo = MagicMock()
    chapter_repo.find_document_id.return_value = document.id
    document_repo = MagicMock()
    document_repo.load.return_value = document
    document_repo.list_all.return_value = [{"id": document.id, "title": "Linchpin", "author": "A"}]
    mentions_repo = MagicMock()
    mentions_repo.paragraph_states.return_value = [{"id": "p1", "state": 1}]

    monkeypatch.setattr(cli, "_build", lambda: (chapter_repo, document_repo, mentions_repo))
    monkeypatch.setattr(cli, "account_id_for", account_id_for)
    return chapter_repo, document_repo, mentions_repo


def test_the_sweep_evaluates_the_documents_pending_chapters(wired, capsys):
    _, _, mentions_repo = wired

    code = cli.main(["sweep", "Linchpin", "--owner", "abby"])

    assert code == 0
    mentions_repo.mark_stale.assert_not_called()
    assert mentions_repo.stamp.called
    out = capsys.readouterr().out
    assert "Opening 1" in out
    assert "pending" in out or "Pending" in out or "state" in out


def test_full_resets_the_verdicts_first(wired):
    _, _, mentions_repo = wired

    code = cli.main(["sweep", "Linchpin", "--owner", "abby", "--full"])

    assert code == 0
    # every chapter is reset: the character chapter and the manuscript chapter
    assert mentions_repo.reset.call_count == 2


def test_an_unknown_document_fails_with_a_message(wired, capsys):
    _, document_repo, _mentions = wired
    document_repo.load.return_value = None  # the id lookup misses
    document_repo.list_all.return_value = []  # and no title matches

    code = cli.main(["sweep", "Nope", "--owner", "abby"])

    assert code == 1
    assert "Nope" in capsys.readouterr().err
