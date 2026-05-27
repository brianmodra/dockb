"""Chapter hydration service that splits chapter text into paragraphs."""

from dockb.models.chapter import Chapter
from dockb.models.paragraph import Paragraph

PARAGRAPH_DELIMITER = "\n\n"


class ChapterHydrator:  # pylint: disable=too-few-public-methods
    """Splits a chapter's text into paragraphs based on double newline delimiters."""

    def hydrate(self, chapter: Chapter) -> None:
        """Split the chapter text into Paragraph objects and attach them.

        Skips empty text chunks that may appear from consecutive delimiters.
        """
        text = chapter.get_text()
        paragraphs = [Paragraph(text=chunk) for chunk in text.split(PARAGRAPH_DELIMITER) if chunk.strip()]
        chapter.paragraphs = paragraphs
