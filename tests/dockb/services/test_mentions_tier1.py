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
from dockb.services.crud_services import ChapterService
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
    return mentions_repo, chapter_repo, document_repo, document


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
            {"id": "p2", "state": 1, "mentions": []},
            {"id": "p3", "state": 2, "mentions": []},
            {"id": "p1", "state": 3, "mentions": []},
            {"id": "p4", "state": 4, "mentions": []},
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


def test_a_job_evaluates_its_scoped_chapter() -> None:
    from dockb.services import mentions as mentions_module

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


def test_the_job_logs_the_mentions_found_for_the_finished_chapter(caplog) -> None:
    from dockb.services import mentions as mentions_module

    mentions_repo = MagicMock()
    mentions_repo.paragraph_states.return_value = [
        {"id": "p1", "state": 3, "index": 0, "mentions": ["k1", "k2"]},
        {"id": "p2", "state": 2, "index": 1, "mentions": []},
    ]
    chapter_repo = MagicMock()
    chapter_repo.load.return_value = _character("c1", "")
    chapter_repo.find_document_id.return_value = "d1"
    document = Document(id="d1", title="Linchpin", state=DataState.SYNC)
    document.chapters.append(Chapter(id="c1", title="Opening 1", state=DataState.SYNC))
    document.chapters.append(_character("k1", "Karakas"))
    document.chapters.append(_character("k2", "Jael"))
    document_repo = MagicMock()
    document_repo.load.return_value = document

    job = mentions_module.MentionsJob(
        chapter_id="c1",
        mentions_repo=mentions_repo,
        chapter_repo=chapter_repo,
        document_repo=document_repo,
        owner="acct-1",
    )
    with caplog.at_level("INFO", logger="dockb.services.mentions"):
        job.run()

    assert any("Mentions for chapter 'Opening 1': 2" in record.message for record in caplog.records)


def _save_service(tmp_path, chapter, mentions_repo, nlp, scheduler=None):
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
        mentions_scheduler=scheduler,
    )
    return service, chapter_repo, doc_repo, store


def test_a_manuscript_save_schedules_its_own_chapter(tmp_path, nlp) -> None:
    chapter = _text_chapter("c1", "Opening 1", act="Act I")
    scheduler = _RecordingScheduler()
    service, _chapter_repo, _doc_repo, _store = _save_service(tmp_path, chapter, MagicMock(), nlp, scheduler)

    service.save_document("c1", '---\nid: c1\n---\n\n<span data-par-id="p1">\nBody.\n</span>', owner="acct-1")

    assert [chapter_id for chapter_id, _make in scheduler.scheduled] == ["c1"]
    job = scheduler.scheduled[0][1]()  # the factory builds the job the run evaluates
    assert job.chapter_id == "c1"


def test_a_character_identity_change_schedules_every_chapter_of_the_document(tmp_path, nlp) -> None:
    """The ambiguity set is document-wide, so every chapter's verdicts are re-judged."""
    ker = _text_chapter("k1", "Jeremiah", category="Character")
    first = _text_chapter("c1", "Opening 1", act="Act I")
    second = _text_chapter("c2", "Opening 2", act="Act I")
    scheduler = _RecordingScheduler()
    service, _chapter_repo, doc_repo, _store = _save_service(tmp_path, ker, MagicMock(), nlp, scheduler)
    doc_repo.load.return_value.chapters.extend([first, second])  # the book has both manuscript chapters

    content = (
        "---\nid: k1\ntitle: Jeremiah\ncategory: Character\n"
        "first_name: Jeremiah\nsurname: Adams\n---\n\n"
        '<span data-par-id="p-k1">\nBody.\n</span>'
    )
    service.save_document("k1", content, owner="acct-1")

    assert sorted(chapter_id for chapter_id, _make in scheduler.scheduled) == ["c1", "c2", "k1"]
    for chapter_id, make_job in scheduler.scheduled:
        job = make_job()
        assert job.chapter_id == chapter_id  # one job per chapter, no document-wide batch


def test_an_identity_change_still_schedules_when_the_repository_loads_fresh_models(tmp_path, nlp) -> None:
    """A real repository builds a new model per load; the save still sees the change.

    The identity verdict must not depend on both loads handing back the same
    object — the save's own chapter model is the one the file's front matter is
    applied to."""
    ker = _text_chapter("k1", "Jeremiah", category="Character")
    first = _text_chapter("c1", "Opening 1", act="Act I")
    second = _text_chapter("c2", "Opening 2", act="Act I")
    scheduler = _RecordingScheduler()
    service, chapter_repo, doc_repo, _store = _save_service(tmp_path, ker, MagicMock(), nlp, scheduler)
    doc_repo.load.return_value.chapters.extend([first, second])
    chapter_repo.load.side_effect = lambda model_id, owner="acct-1": ker.model_copy(deep=True)

    content = (
        "---\nid: k1\ntitle: Jeremiah\ncategory: Character\n"
        "first_name: Jeremiah\nsurname: Adams\n---\n\n"
        '<span data-par-id="p-k1">\nBody.\n</span>'
    )
    service.save_document("k1", content, owner="acct-1")

    assert sorted(chapter_id for chapter_id, _make in scheduler.scheduled) == ["c1", "c2", "k1"]


def test_a_character_save_without_identity_change_triggers_nothing(tmp_path, nlp) -> None:
    chapter = Chapter(id="k1", title="Jeremiah", category="Character", state=DataState.SYNC)
    chapter.first_name = "Jeremiah"
    paragraph = Paragraph(id="p1", state=DataState.SYNC)
    sentence = Sentence(state=DataState.SYNC)
    sentence.tokens.append(Token(text="Body.", trailing_ws=" ", state=DataState.SYNC))
    paragraph.sentences.append(sentence)
    chapter.paragraphs.append(paragraph)
    scheduler = _RecordingScheduler()
    service, _chapter_repo, _doc_repo, _store = _save_service(tmp_path, chapter, MagicMock(), nlp, scheduler)

    content = (
        "---\nid: k1\ntitle: Jeremiah\ncategory: Character\n"
        'first_name: Jeremiah\n---\n\n<span data-par-id="p1">\nBody text changed.\n</span>'
    )
    service.save_document("k1", content, owner="acct-1")

    assert not scheduler.scheduled


def test_a_longer_adjacent_run_beats_the_defeated_shorter_match() -> None:
    # "Jael Adams": the two-token run is Jael's name; the nickname "Adams"
    # (Jeremiah's) is defeated — no verdict for Jeremiah, one for Jael.
    mentions_repo, chapter_repo, document_repo, document = _fixture([{"id": "p5", "state": 1}])
    jael = _character("k2", "Jael", first_name="Jael", surname="Adams")
    document.chapters.append(jael)
    chapter = document.chapters[0]
    chapter.paragraphs.append(_paragraph("p5", [("Jael", POS.PROPN), ("Adams", POS.PROPN), ("waited", POS.VERB)]))

    evaluate_chapter_tier1("c1", owner=_OWNER, mentions_repo=mentions_repo, chapter_repo=chapter_repo, document_repo=document_repo)

    stamped = mentions_repo.stamp.call_args
    assert stamped is not None and stamped.args[0] == "p5"
    assert [v["character_id"] for v in stamped.args[1]] == ["k2"]


def test_the_full_name_run_beats_both_the_first_name_and_the_nickname() -> None:
    mentions_repo, chapter_repo, document_repo, document = _fixture([{"id": "p6", "state": 1}])
    chapter = document.chapters[0]
    chapter.paragraphs.append(
        _paragraph(
            "p6",
            [("Jeremiah", POS.PROPN), ("Edgar", POS.PROPN), ("Adams", POS.PROPN), ("spoke", POS.VERB)],
        )
    )

    evaluate_chapter_tier1("c1", owner=_OWNER, mentions_repo=mentions_repo, chapter_repo=chapter_repo, document_repo=document_repo)

    stamped = mentions_repo.stamp.call_args
    assert stamped is not None and stamped.args[0] == "p6"
    assert [v["character_id"] for v in stamped.args[1]] == ["k1"]
    assert stamped.kwargs["checked_at"]


def test_a_shared_name_with_no_completing_run_stays_pending() -> None:
    # "Adams entered" alone: shared by Jeremiah (nickname) and Jael (surname).
    mentions_repo, chapter_repo, document_repo, document = _fixture([{"id": "p3", "state": 1}])
    jael = _character("k2", "Jael", first_name="Jael", surname="Adams")
    document.chapters.append(jael)

    evaluate_chapter_tier1("c1", owner=_OWNER, mentions_repo=mentions_repo, chapter_repo=chapter_repo, document_repo=document_repo)

    mentions_repo.stamp.assert_not_called()  # pending for tier 3


def test_a_possessive_clitic_does_not_block_the_name_match() -> None:
    mentions_repo, chapter_repo, document_repo, document = _fixture([{"id": "p7", "state": 1}])
    chapter = document.chapters[0]
    # "Jael's" tokenizes as Jael + 's
    paragraph = Paragraph(id="p7", state=DataState.SYNC)
    sentence = Sentence(state=DataState.SYNC)
    sentence.tokens.append(Token(text="Jael", trailing_ws="", pos=POS.PROPN, state=DataState.SYNC))
    sentence.tokens.append(Token(text="'s", trailing_ws=" ", pos=POS.PART, state=DataState.SYNC))
    sentence.tokens.append(Token(text="brother", trailing_ws=" ", pos=POS.NOUN, state=DataState.SYNC))
    paragraph.sentences.append(sentence)
    chapter.paragraphs.append(paragraph)
    jael = _character("k2", "Jael", first_name="Jael", surname="Adams")
    document.chapters.append(jael)

    evaluate_chapter_tier1("c1", owner=_OWNER, mentions_repo=mentions_repo, chapter_repo=chapter_repo, document_repo=document_repo)

    stamped = mentions_repo.stamp.call_args
    assert stamped is not None and stamped.args[0] == "p7"
    assert [v["character_id"] for v in stamped.args[1]] == ["k2"]


def test_the_evaluation_refreshes_the_chapters_mention_rollup() -> None:
    mentions_repo, chapter_repo, document_repo, _document = _fixture([{"id": "p2", "state": 1}])

    def states_evolve(*_args, **_kwargs):
        # the graph's view: pending until tier 1 stamps it, then a valid verdict
        if mentions_repo.stamp.call_args_list:
            return [{"id": "p2", "state": 3, "index": 0, "mentions": ["k1"]}]
        return [{"id": "p2", "state": 1, "index": 0, "mentions": []}]

    mentions_repo.paragraph_states.side_effect = states_evolve

    evaluate_chapter_tier1("c1", owner=_OWNER, mentions_repo=mentions_repo, chapter_repo=chapter_repo, document_repo=document_repo)

    mentions_repo.stamp_chapter.assert_called_once_with("c1", ["k1"], owner=_OWNER)


def test_a_cancelled_job_evaluates_nothing() -> None:
    import threading

    from dockb.services import mentions as mentions_module

    mentions_repo, chapter_repo, document_repo, _document = _fixture([{"id": "p2", "state": 1}])

    job = mentions_module.MentionsJob(
        chapter_id="c1",
        mentions_repo=mentions_repo,
        chapter_repo=chapter_repo,
        document_repo=document_repo,
        owner=_OWNER,
    )
    job.cancel = threading.Event()
    job.cancel.set()
    job.run()

    mentions_repo.paragraph_states.assert_not_called()  # cancelled before it read anything


def test_a_job_cancelled_between_paragraphs_stamps_nothing_more() -> None:
    import threading

    from dockb.services import mentions as mentions_module

    mentions_repo, chapter_repo, document_repo, _document = _fixture([{"id": "p2", "state": 1}, {"id": "p4", "state": 1}])
    job = mentions_module.MentionsJob(
        chapter_id="c1",
        mentions_repo=mentions_repo,
        chapter_repo=chapter_repo,
        document_repo=document_repo,
        owner=_OWNER,
    )
    job.cancel = threading.Event()

    def cancel_after_first_stamp(*_args, **_kwargs):
        job.cancel.set()

    mentions_repo.stamp.side_effect = cancel_after_first_stamp
    job.run()

    stamped_ids = [call.args[0] for call in mentions_repo.stamp.call_args_list]
    assert stamped_ids == ["p2"]  # p4's paragraph is left for the successor run
    mentions_repo.stamp_chapter.assert_not_called()  # a cancelled run refreshes no rollup


class _RecordingScheduler:  # pylint: disable=too-few-public-methods
    """A scheduler stand-in that records what the save triggers scheduled."""

    def __init__(self) -> None:
        self.scheduled: list[tuple[str, object]] = []  # (chapter_id, make_job)

    def schedule(self, chapter_id: str, make_job) -> None:
        self.scheduled.append((chapter_id, make_job))


def _text_chapter(chapter_id: str, title: str, act: str = "", category: str = "Chapter") -> Chapter:
    """A chapter whose one paragraph carries the default body text."""
    chapter = Chapter(id=chapter_id, title=title, act=act, category=category, state=DataState.SYNC)
    paragraph = Paragraph(id=f"p-{chapter_id}", state=DataState.SYNC)
    sentence = Sentence(state=DataState.SYNC)
    sentence.tokens.append(Token(text="Body.", trailing_ws=" ", state=DataState.SYNC))
    paragraph.sentences.append(sentence)
    chapter.paragraphs.append(paragraph)
    return chapter
