"""Tier 2 of the mention pipeline: the model judges the ambiguous candidates."""

from unittest.mock import MagicMock

from dockb.models.base import DataState
from dockb.models.chapter import Chapter
from dockb.models.document import Document
from dockb.models.paragraph import Paragraph
from dockb.models.sentence import Sentence
from dockb.models.token import POS, Token
from dockb.services.mentions import judge_ambiguous


def _candidate(key: str, sentence: str, character_title: str, names: list[str]) -> dict:
    return {"key": key, "sentence": sentence, "character_title": character_title, "names": names}


def test_one_call_judges_every_candidate_and_returns_the_verdicts() -> None:
    calls = []

    def complete(prompt: str) -> str:
        calls.append(prompt)
        return '{"1": true, "2": false}'

    verdicts = judge_ambiguous(
        [
            _candidate("p1:k1", "Adams entered the study.", "Jeremiah", ["Jeremiah", "Adams"]),
            _candidate("p2:k2", "Mordecai waited outside.", "Tobias", ["Tobias", "Mordecai"]),
        ],
        complete=complete,
    )

    assert verdicts == {"p1:k1": True, "p2:k2": False}
    assert len(calls) == 1
    assert "1. Adams entered the study." in calls[0]
    assert "Jeremiah" in calls[0]
    assert "2. Mordecai waited outside." in calls[0]


def test_a_model_or_network_failure_is_benign() -> None:
    def complete(prompt: str) -> str:
        raise RuntimeError("the model is down")

    verdicts = judge_ambiguous(
        [_candidate("p1:k1", "Adams entered.", "Jeremiah", ["Adams"])],
        complete=complete,
    )

    assert verdicts == {"p1:k1": None}  # unresolved, not false


def test_an_unparseable_answer_is_benign() -> None:
    verdicts = judge_ambiguous(
        [_candidate("p1:k1", "Adams entered.", "Jeremiah", ["Adams"])],
        complete=lambda prompt: "I cannot help with that.",
    )

    assert verdicts == {"p1:k1": None}


def test_no_candidates_makes_no_call() -> None:
    def complete(prompt: str) -> str:
        raise AssertionError("the model must not be called")

    assert judge_ambiguous([], complete=complete) == {}


def _paragraph(par_id: str, words_and_pos: list[tuple[str, POS]]) -> Paragraph:
    paragraph = Paragraph(id=par_id, state=DataState.SYNC)
    sentence = Sentence(state=DataState.SYNC)
    for text, pos in words_and_pos:
        sentence.tokens.append(Token(text=text, trailing_ws=" ", pos=pos, state=DataState.SYNC))
    paragraph.sentences.append(sentence)
    return paragraph


def _ambiguity_fixture(monkeypatch):
    """A document whose 'Adams' is ambiguous between Jeremiah and Jael."""

    document = Document(id="d1", state=DataState.SYNC)
    chapter = Chapter(id="c1", title="Opening 1", state=DataState.SYNC)
    chapter.paragraphs.append(_paragraph("p1", [("Adams", POS.PROPN), ("waited", POS.VERB)]))
    document.chapters.append(chapter)
    jeremiah = Chapter(id="k1", title="Jeremiah", category="Character", state=DataState.SYNC)
    jeremiah.first_name = "Jeremiah"
    jeremiah.surname = "Adams"
    jeremiah.nicknames = ["Adams"]
    jael = Chapter(id="k2", title="Jael", category="Character", state=DataState.SYNC)
    jael.first_name = "Jael"
    jael.surname = "Adams"
    document.chapters.append(jeremiah)
    document.chapters.append(jael)

    mentions_repo = MagicMock()
    mentions_repo.paragraph_states.return_value = [{"id": "p1", "state": 1}]
    chapter_repo = MagicMock()
    chapter_repo.load.return_value = chapter
    chapter_repo.find_document_id.return_value = "d1"
    document_repo = MagicMock()
    document_repo.load.return_value = document

    monkeypatch.setenv("OPENAI_API_KEY", "key-test")
    return mentions_repo, chapter_repo, document_repo


def test_a_true_verdict_stamps_the_paragraph_as_a_mention(monkeypatch) -> None:
    from dockb.services.mentions import evaluate_chapter_tier2

    mentions_repo, chapter_repo, document_repo = _ambiguity_fixture(monkeypatch)

    evaluate_chapter_tier2(
        "c1",
        owner="acct-1",
        mentions_repo=mentions_repo,
        chapter_repo=chapter_repo,
        document_repo=document_repo,
        complete=lambda prompt: '{"1": true, "2": false}',
    )

    stamped = mentions_repo.stamp.call_args
    assert stamped is not None
    assert stamped.args[0] == "p1"
    assert stamped.kwargs["checked_at"]
    assert stamped.args[1] == [{"character_id": "k1", "method": "model", "confidence": 1.0}]


def test_a_false_verdict_stamps_the_paragraph_as_mentioning_nobody(monkeypatch) -> None:
    from dockb.services.mentions import evaluate_chapter_tier2

    mentions_repo, chapter_repo, document_repo = _ambiguity_fixture(monkeypatch)

    evaluate_chapter_tier2(
        "c1",
        owner="acct-1",
        mentions_repo=mentions_repo,
        chapter_repo=chapter_repo,
        document_repo=document_repo,
        complete=lambda prompt: '{"1": false, "2": false}',
    )

    stamped = mentions_repo.stamp.call_args
    assert stamped is not None
    assert stamped.args[1] == []
    assert stamped.kwargs["checked_at"]


def test_an_unresolved_candidate_leaves_the_paragraph_unstamped(monkeypatch) -> None:
    from dockb.services.mentions import evaluate_chapter_tier2

    mentions_repo, chapter_repo, document_repo = _ambiguity_fixture(monkeypatch)

    evaluate_chapter_tier2(
        "c1",
        owner="acct-1",
        mentions_repo=mentions_repo,
        chapter_repo=chapter_repo,
        document_repo=document_repo,
        complete=lambda prompt: "no thanks",
    )

    mentions_repo.stamp.assert_not_called()


def test_a_missing_api_key_makes_no_call(monkeypatch) -> None:
    from dockb.services.mentions import evaluate_chapter_tier2

    mentions_repo, chapter_repo, document_repo = _ambiguity_fixture(monkeypatch)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    complete = MagicMock(side_effect=AssertionError("no key, no call"))

    evaluate_chapter_tier2(
        "c1",
        owner="acct-1",
        mentions_repo=mentions_repo,
        chapter_repo=chapter_repo,
        document_repo=document_repo,
        complete=complete,
    )

    complete.assert_not_called()
    mentions_repo.stamp.assert_not_called()


class _Span:  # pylint: disable=too-few-public-methods
    """One entity span of the fake spaCy doc."""

    def __init__(self, text: str, label: str) -> None:
        self.text = text
        self.label_ = label


class _FakeDoc:  # pylint: disable=too-few-public-methods
    """A spaCy doc stand-in carrying only its entity spans."""

    def __init__(self, spans: list[_Span]) -> None:
        self.ents = spans


def _fake_nlp(spans: list[_Span]):
    """A spaCy model stand-in that always returns *spans* as the doc's entities."""

    def nlp(_text: str) -> _FakeDoc:
        return _FakeDoc(spans)

    return nlp


def _ner_fixture(monkeypatch):
    """'Adams waited.' is pending; the fake NER sees a full-name PERSON span."""
    mentions_repo, chapter_repo, document_repo = _ambiguity_fixture(monkeypatch)
    nlp = _fake_nlp([_Span("Jeremiah Adams", "PERSON")])
    return mentions_repo, chapter_repo, document_repo, nlp


def test_a_person_span_matching_one_candidate_resolves_it_without_the_model(monkeypatch) -> None:
    from dockb.services.mentions import evaluate_chapter_tier2

    mentions_repo, chapter_repo, document_repo, nlp = _ner_fixture(monkeypatch)
    # the model is only asked about k2 (Jael): the span named Jeremiah exactly
    complete = MagicMock(return_value='{"1": false}')

    evaluate_chapter_tier2(
        "c1",
        owner="acct-1",
        mentions_repo=mentions_repo,
        chapter_repo=chapter_repo,
        document_repo=document_repo,
        complete=complete,
        nlp=nlp,
    )

    assert complete.call_count == 1
    stamped = mentions_repo.stamp.call_args
    assert stamped is not None
    assert stamped.args[0] == "p1"
    assert stamped.kwargs["checked_at"]
    assert [v["character_id"] for v in stamped.args[1]] == ["k1"]
    assert all(v["method"] == "name" for v in stamped.args[1])


def test_a_person_span_two_candidates_claim_does_not_resolve(monkeypatch) -> None:
    from dockb.services.mentions import evaluate_chapter_tier2

    mentions_repo, chapter_repo, document_repo = _ambiguity_fixture(monkeypatch)
    nlp = _fake_nlp([_Span("Adams", "PERSON")])

    evaluate_chapter_tier2(
        "c1",
        owner="acct-1",
        mentions_repo=mentions_repo,
        chapter_repo=chapter_repo,
        document_repo=document_repo,
        complete=lambda prompt: '{"1": true, "2": false}',
        nlp=nlp,
    )

    stamped = mentions_repo.stamp.call_args
    assert stamped is not None
    assert stamped.kwargs["checked_at"]  # the model settled it
    assert [v["method"] for v in stamped.args[1]] == ["model"]


def test_no_nlp_goes_straight_to_the_model(monkeypatch) -> None:
    from dockb.services.mentions import evaluate_chapter_tier2

    mentions_repo, chapter_repo, document_repo = _ambiguity_fixture(monkeypatch)

    evaluate_chapter_tier2(
        "c1",
        owner="acct-1",
        mentions_repo=mentions_repo,
        chapter_repo=chapter_repo,
        document_repo=document_repo,
        complete=lambda prompt: '{"1": true, "2": false}',
        nlp=None,
    )

    stamped = mentions_repo.stamp.call_args
    assert stamped is not None and stamped.kwargs["checked_at"]
