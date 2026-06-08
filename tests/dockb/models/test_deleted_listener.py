"""Tests for OnDeletedListener mechanism on DockbModel."""

import pytest

from dockb.models.base import OnDeletedListener
from dockb.models.chapter import Chapter
from dockb.models.document import Document
from dockb.models.paragraph import Paragraph
from dockb.models.sentence import Sentence
from dockb.models.token import Token
from dockb.models.utils.dockb_collection import DockbModelBase

# ---------------------------------------------------------------------------
# Helper listeners for test assertions
# ---------------------------------------------------------------------------


class CallRecorder(OnDeletedListener):  # pylint: disable=too-few-public-methods
    """Records every on_deleted call and returns a configurable value."""

    def __init__(self, *, result: bool = False):
        self.calls: list[DockbModelBase] = []
        self.result = result

    def on_deleted(self, model: DockbModelBase) -> bool:
        self.calls.append(model)
        return self.result


# ---------------------------------------------------------------------------
# Listener contract
# ---------------------------------------------------------------------------


def test_listener_called_when_parent_set_to_none(document):
    recorder = CallRecorder()
    doc = Document()
    doc.add_on_deleted_listener(recorder)
    doc.set_parent(document, document)

    doc.set_parent(document, None)

    assert len(recorder.calls) == 1
    assert recorder.calls[0] is doc


def test_listener_not_called_on_first_parenting(document):
    doc = Document()
    recorder = CallRecorder()
    doc.add_on_deleted_listener(recorder)

    doc.set_parent(document, document)

    assert len(recorder.calls) == 0


def test_listener_not_called_when_reparented(document, chapter):
    """Moving from one parent to another should not trigger on_deleted."""
    recorder = CallRecorder()
    chapter.add_on_deleted_listener(recorder)

    document.chapters.append(chapter)
    doc2 = Document()
    doc2.chapters.append(chapter)

    assert len(recorder.calls) == 0


def test_no_listener_does_not_error(document):
    doc = Document()
    doc.set_parent(document, document)
    doc.set_parent(document, None)


# ---------------------------------------------------------------------------
# Listener result (break / continue)
# ---------------------------------------------------------------------------


def test_listener_returning_true_stops_propagation(document):
    first = CallRecorder(result=True)
    second = CallRecorder(result=False)
    model = Document()
    model.add_on_deleted_listener(first)
    model.add_on_deleted_listener(second)
    model.set_parent(document, document)

    model.set_parent(document, None)

    assert len(first.calls) == 1
    assert len(second.calls) == 0


def test_listener_returning_false_allows_next_listener(document):
    first = CallRecorder(result=False)
    second = CallRecorder(result=False)
    model = Document()
    model.add_on_deleted_listener(first)
    model.add_on_deleted_listener(second)
    model.set_parent(document, document)

    model.set_parent(document, None)

    assert len(first.calls) == 1
    assert len(second.calls) == 1


def test_multiple_listeners_all_see_same_model(document):
    a = CallRecorder()
    b = CallRecorder()
    model = Document()
    model.add_on_deleted_listener(a)
    model.add_on_deleted_listener(b)
    model.set_parent(document, document)

    model.set_parent(document, None)

    assert a.calls[0] is model
    assert b.calls[0] is model


# ---------------------------------------------------------------------------
# Triggered via DockbCollection operations
# ---------------------------------------------------------------------------


def test_triggered_on_collection_delete(document, chapter):
    recorder = CallRecorder()
    chapter.add_on_deleted_listener(recorder)
    document.chapters.append(chapter)

    document.chapters.delete(chapter.id)

    assert len(recorder.calls) == 1
    assert recorder.calls[0] is chapter


def test_triggered_on_collection_clear(document, chapter):
    recorder = CallRecorder()
    chapter.add_on_deleted_listener(recorder)
    document.chapters.append(chapter)

    document.chapters.clear()

    assert len(recorder.calls) == 1


def test_triggered_on_collection_append_replacing_key(document):
    ch1 = Chapter()
    ch2 = Chapter()
    # Make ch2 share the same id as ch1 to force a replacement
    object.__setattr__(ch2, "id", ch1.id)

    recorder = CallRecorder()
    ch1.add_on_deleted_listener(recorder)
    document.chapters.append(ch1)

    document.chapters.append(ch2)

    assert len(recorder.calls) == 1
    assert recorder.calls[0] is ch1


def test_triggered_on_delitem(document, chapter):
    recorder = CallRecorder()
    chapter.add_on_deleted_listener(recorder)
    document.chapters.append(chapter)

    del document.chapters[chapter.id]

    assert len(recorder.calls) == 1


# ---------------------------------------------------------------------------
# Listener works on all model types
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "model_factory",
    [
        pytest.param(Document, id="Document"),
        pytest.param(Chapter, id="Chapter"),
        pytest.param(Paragraph, id="Paragraph"),
        pytest.param(Sentence, id="Sentence"),
        pytest.param(Token, id="Token"),
    ],
)
def test_all_model_types_support_listener(document, model_factory):
    model = model_factory()
    recorder = CallRecorder()
    model.add_on_deleted_listener(recorder)
    model.set_parent(document, document)

    model.set_parent(document, None)

    assert len(recorder.calls) == 1
    assert recorder.calls[0] is model


# ---------------------------------------------------------------------------
# Listener across the parent-child hierarchy
# ---------------------------------------------------------------------------


def test_paragraph_unparented_via_chapter_clear():
    ch = Chapter()
    p = Paragraph()
    recorder = CallRecorder()
    p.add_on_deleted_listener(recorder)
    ch.paragraphs.append(p)

    ch.paragraphs.clear()

    assert len(recorder.calls) == 1


def test_token_unparented_via_sentence_delete():
    s = Sentence()
    t = Token()
    recorder = CallRecorder()
    t.add_on_deleted_listener(recorder)
    s.tokens.append(t)

    s.tokens.delete(t.id)

    assert len(recorder.calls) == 1


# ---------------------------------------------------------------------------
# _listeners is a PrivateAttr (not part of model fields / serialization)
# ---------------------------------------------------------------------------


def test_listeners_not_in_model_fields():
    model = Document()
    assert "_listeners" not in Document.model_fields  # pylint: disable=unsupported-membership-test
    assert "_listeners" not in model.__dict__
