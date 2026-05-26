import pytest

from dockb.models.paragraph import Paragraph
from dockb.services.semantics.paragraph_hydrator import ParagraphHydrator


def test_rehydrate_a_paragraph_creates_the_child_sentences(nlp):
    sentence1 = "This is a very short sentence."
    sentence2 = "This is another simple sentence."
    doc_text = f"{sentence1} {sentence2}"
    paragraph = Paragraph()
    paragraph.set_text(doc_text)
    hydrator = ParagraphHydrator(nlp=nlp)
    hydrator.hydrate(paragraph)
    assert paragraph.sentences[0].get_text() == sentence1
    assert paragraph.sentences[1].get_text() == sentence2


@pytest.mark.parametrize(
    "sentence1, sentence2",
    [
        pytest.param("This is a very short sentence!", "This is another simple sentence?", id="exclamation_question"),
        pytest.param("This is exciting!", "Is that really true?", id="exclamation_question_2"),
        pytest.param("She said hello.", "He replied goodbye.", id="period_period"),
        pytest.param("Wait a second!", "Really?", id="exclamation_question_3"),
        pytest.param("The end...", "Or is it?", id="ellipsis_question"),
        pytest.param("And another... with elipses.", "The story continues.", id="ellipsis_period"),
        pytest.param('She said, "Hello, I am here."', "He nodded.", id="quoted_period"),
        pytest.param("Dr. Smith arrived early.", "The meeting started.", id="abbreviation_dr"),
        pytest.param("See e.g. the example.", "It works well.", id="abbreviation_eg"),
        pytest.param("It was etc. etc.", "The end.", id="abbreviation_etc"),
    ],
)
def test_rehydrate_a_paragraph_creates_the_child_sentences_using_other_delimiter_punctuation(nlp, sentence1, sentence2):
    doc_text = f"{sentence1} {sentence2}"
    paragraph = Paragraph()
    paragraph.set_text(doc_text)
    hydrator = ParagraphHydrator(nlp=nlp)
    hydrator.hydrate(paragraph)
    assert paragraph.sentences[0].get_text() == sentence1
    assert paragraph.sentences[1].get_text() == sentence2


def test_rehydrate_a_paragraph_creates_the_child_sentences_but_not_empty_sentences(nlp):
    sentence1 = "This is a very short sentence."
    sentence2 = "This is another simple sentence."
    doc_text = f"{sentence1} {sentence2}..."
    paragraph = Paragraph()
    paragraph.set_text(doc_text)
    hydrator = ParagraphHydrator(nlp=nlp)
    hydrator.hydrate(paragraph)
    assert paragraph.sentences[0].get_text() == sentence1
    assert len(paragraph.sentences) == 2


def test_rehydrate_a_paragraph_creates_the_child_sentences_including_dr_etc(nlp):
    sentence1 = "This is a very short sentence about Dr. Zhivago."
    sentence2 = "And e.g. another ... simple \nsentence etc. etc."
    doc_text = f"{sentence1} {sentence2}"
    paragraph = Paragraph()
    paragraph.set_text(doc_text)
    hydrator = ParagraphHydrator(nlp=nlp)
    hydrator.hydrate(paragraph)
    assert paragraph.sentences[0].get_text() == sentence1
    assert paragraph.sentences[1].get_text() == sentence2


def test_rehydrate_a_paragraph_ignores_stray_punctuation_between_sentences(nlp):
    doc_text = "This is a short sentence. . And another sentence."
    paragraph = Paragraph()
    paragraph.set_text(doc_text)
    hydrator = ParagraphHydrator(nlp=nlp)
    hydrator.hydrate(paragraph)
    assert len(paragraph.sentences) == 2
