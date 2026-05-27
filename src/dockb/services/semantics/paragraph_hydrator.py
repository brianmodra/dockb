"""Paragraph hydration service that splits paragraph text into sentences using spaCy."""

from spacy.language import Language

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
        sentences = [Sentence(text=sent.text) for sent in doc.sents if sent.text.strip()]
        paragraph.sentences = sentences
