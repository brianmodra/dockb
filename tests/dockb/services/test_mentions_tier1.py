"""Tier 1 of the mention pipeline: the deterministic name-set evaluation."""

from unittest.mock import MagicMock

from dockb.infrastructure.document_store.factory import DocumentStoreFactory
from dockb.infrastructure.document_store.store import DocumentStore
from dockb.models.base import DataState
from dockb.models.chapter import Chapter
from dockb.models.document import Document
from dockb.models.paragraph import Paragraph
from dockb.models.sentence import Sentence
from dockb.models.token import POS, Token
from dockb.services import crud_services as crud_services_module
from dockb.services.crud_services import ChapterService
from dockb.services.mentions import evaluate_chapter_tier1, run_mentions_async

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


def test_a_chapter_save_triggers_a_chapter_scoped_evaluation(monkeypatch) -> None:
    from dockb.services import mentions as mentions_module

    triggered = []
    monkeypatch.setattr(mentions_module, "run_mentions_async", lambda *args: triggered.append(args[0]))

    chapter = _character("k1", "Jeremiah", first_name="Jeremiah")
    document = Document(id="d1", state=DataState.SYNC)
    document.chapters.append(chapter)
    mentions_repo = MagicMock()
    mentions_repo.paragraph_states.return_value = []
    chapter_repo = MagicMock()
    chapter_repo.load.return_value = chapter
    chapter_repo.find_document_id.return_value = "d1"
    document_repo = MagicMock()
    document_repo.load.return_value = document

    job = mentions_module.MentionsJob(
        chapter_id="k1",
        mentions_repo=mentions_repo,
        chapter_repo=chapter_repo,
        document_repo=document_repo,
        owner="acct-1",
    )
    job.run()

    assert mentions_repo.paragraph_states.call_count >= 1


def test_run_mentions_async_runs_the_job_on_a_daemon_thread() -> None:
    import threading

    done = threading.Event()
    job = MagicMock()
    job.run.side_effect = done.set

    run_mentions_async(job)

    assert done.wait(5)
    assert job.run.called


def _save_service(tmp_path, chapter, mentions_repo, nlp):
    chapter_repo = MagicMock()
    chapter_repo.load.return_value = chapter
    chapter_repo.find_document_id.return_value = "d1"
    doc_repo = MagicMock()
    document = Document(id="d1", title="T", author="A", owner="acct-1", state=DataState.SYNC)
    document.chapters.append(chapter)
    doc_repo.load.return_value = document
    doc_repo.load_shell.return_value = document
    store = DocumentStore(base_dir=tmp_path, account_id="acct-1")
    store.write_chapter("T", chapter.act, chapter.title, chapter.get_text() or "body")
    store.git_commit("T", "materialize: doc")
    service = ChapterService(
        uow_factory=MagicMock(),
        chapter_repo=chapter_repo,
        document_repo=doc_repo,
        document_store_factory=DocumentStoreFactory(base_dir=tmp_path),
        nlp=nlp,
        mentions_repo=mentions_repo,
    )
    return service, chapter_repo, doc_repo, store


def test_a_manuscript_save_triggers_a_chapter_scoped_mentions_job(tmp_path, monkeypatch, nlp) -> None:
    chapter = Chapter(id="c1", title="Opening 1", act="Act I", state=DataState.SYNC)
    paragraph = Paragraph(id="p1", state=DataState.SYNC)
    sentence = Sentence(state=DataState.SYNC)
    sentence.tokens.append(Token(text="Body.", trailing_ws=" ", state=DataState.SYNC))
    paragraph.sentences.append(sentence)
    chapter.paragraphs.append(paragraph)
    mentions_repo = MagicMock()
    mentions_repo.paragraph_states.return_value = []
    mentions_repo.stamp.side_effect = None
    service, _chapter_repo, _doc_repo, _store = _save_service(tmp_path, chapter, mentions_repo, nlp)
    triggered = []
    monkeypatch.setattr(crud_services_module, "run_mentions_async", triggered.append)

    service.save_document("c1", '---\nid: c1\n---\n\n<span data-par-id="p1">\nBody.\n</span>', owner="acct-1")

    assert len(triggered) == 1
    assert triggered[0].chapter_id == "c1"
    assert triggered[0].document_id is None


def test_a_character_identity_change_triggers_a_document_scoped_job(tmp_path, monkeypatch, nlp) -> None:
    chapter = Chapter(id="k1", title="Jeremiah", category="Character", state=DataState.SYNC)
    paragraph = Paragraph(id="p1", state=DataState.SYNC)
    sentence = Sentence(state=DataState.SYNC)
    sentence.tokens.append(Token(text="Body.", trailing_ws=" ", state=DataState.SYNC))
    paragraph.sentences.append(sentence)
    chapter.paragraphs.append(paragraph)
    mentions_repo = MagicMock()
    mentions_repo.paragraph_states.return_value = []
    service, _chapter_repo, _doc_repo, _store = _save_service(tmp_path, chapter, mentions_repo, nlp)
    # the saved file's front matter renames the character's surname
    triggered = []
    monkeypatch.setattr(crud_services_module, "run_mentions_async", triggered.append)

    content = (
        "---\nid: k1\ntitle: Jeremiah\ncategory: Character\n"
        "first_name: Jeremiah\nsurname: Adams\n---\n\n"
        '<span data-par-id="p1">\nBody.\n</span>'
    )
    service.save_document("k1", content, owner="acct-1")

    assert len(triggered) == 1
    assert triggered[0].document_id == "d1"
    assert triggered[0].chapter_id is None


def test_a_character_save_without_identity_change_triggers_nothing(tmp_path, monkeypatch, nlp) -> None:
    chapter = Chapter(id="k1", title="Jeremiah", category="Character", state=DataState.SYNC)
    chapter.first_name = "Jeremiah"
    paragraph = Paragraph(id="p1", state=DataState.SYNC)
    sentence = Sentence(state=DataState.SYNC)
    sentence.tokens.append(Token(text="Body.", trailing_ws=" ", state=DataState.SYNC))
    paragraph.sentences.append(sentence)
    chapter.paragraphs.append(paragraph)
    mentions_repo = MagicMock()
    mentions_repo.paragraph_states.return_value = []
    service, _chapter_repo, _doc_repo, _store = _save_service(tmp_path, chapter, mentions_repo, nlp)
    triggered = []
    monkeypatch.setattr(crud_services_module, "run_mentions_async", triggered.append)

    content = (
        "---\nid: k1\ntitle: Jeremiah\ncategory: Character\n"
        'first_name: Jeremiah\n---\n\n<span data-par-id="p1">\nBody text changed.\n</span>'
    )
    service.save_document("k1", content, owner="acct-1")

    assert not triggered
