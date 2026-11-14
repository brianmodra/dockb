"""Paragraph hydration service that splits paragraph text into sentences using spaCy."""

from spacy.language import Language

from dockb.models.formatting import slice_runs
from dockb.models.paragraph import Paragraph
from dockb.models.sentence import Sentence


class ParagraphHydrator:  # pylint: disable=too-few-public-methods
    """Splits a paragraph's text into sentences using spaCy's sentencizer."""

    def __init__(self, nlp: Language) -> None:
        self._nlp = nlp

    def hydrate(self, paragraph: Paragraph) -> None:
        """Split the paragraph text into Sentence objects using spaCy and attach them.

        Skips empty sentences that may appear from trailing punctuation.
        """
        text = paragraph.get_text()
        doc = self._nlp(text)
        runs = paragraph.format_runs
        sentences = []
        for sent in doc.sents:
            if not sent.text.strip():
                continue
            sentence = Sentence(text=sent.text)
            if runs:
                sentence.format_runs = slice_runs(runs, sent.start_char, sent.end_char)
            sentences.append(sentence)
        paragraph.sentences[:] = sentences
        paragraph.format_runs = []
