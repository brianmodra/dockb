import pytest

from dockb.models.formatting import FormatRun, Style, Weight
from dockb.models.paragraph import Paragraph
from dockb.services.semantics.doc_cache import DocCache
from dockb.services.semantics.paragraph_hydrator import ParagraphHydrator
from dockb.services.semantics.sentence_tokenizer import SentenceTokenizer


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


def test_hydrate_splits_paragraph_runs_onto_the_sentences(nlp):
    paragraph = Paragraph(text="Hello world. Goodbye moon.")
    paragraph.format_runs = [
        FormatRun(0, 6, weight=Weight.BOLD),
        FormatRun(13, 20, style=Style.ITALIC),
    ]

    ParagraphHydrator(nlp=nlp).hydrate(paragraph)

    assert not paragraph.format_runs
    assert paragraph.sentences[0].format_runs == [FormatRun(0, 6, weight=Weight.BOLD)]
    assert paragraph.sentences[1].format_runs == [FormatRun(0, 7, style=Style.ITALIC)]


def test_hydrate_clips_a_run_that_straddles_a_sentence_boundary(nlp):
    paragraph = Paragraph(text="Hello world. Goodbye moon.")
    paragraph.format_runs = [FormatRun(0, 15, style=Style.UNDERLINE)]

    ParagraphHydrator(nlp=nlp).hydrate(paragraph)

    assert paragraph.sentences[0].format_runs == [FormatRun(0, 12, style=Style.UNDERLINE)]
    assert paragraph.sentences[1].format_runs == [FormatRun(0, 2, style=Style.UNDERLINE)]


def test_hydrate_then_tokenize_keeps_formatting_across_a_sentence_split(nlp):
    paragraph = Paragraph(text="Hello world. Goodbye moon.")
    paragraph.format_runs = [FormatRun(0, 15, style=Style.UNDERLINE)]
    ParagraphHydrator(nlp=nlp).hydrate(paragraph)

    tokenizer = SentenceTokenizer()
    doc_cache = DocCache(nlp)
    for sentence in paragraph.sentences:
        sentence.tokens[:] = tokenizer.tokenize(
            sentence.get_text(),
            doc_cache,
            sentence.format_runs,
        )

    assert paragraph.sentences[0].tokens[0].style is Style.UNDERLINE
    assert paragraph.sentences[1].tokens[0].style is Style.UNDERLINE
