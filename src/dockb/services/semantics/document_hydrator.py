"""Document hydration service that splits document text into chapters."""

from dockb.models.chapter import Chapter
from dockb.models.document import Document

CHAPTER_DELIMITER = "\f\f"


class DocumentHydrator:  # pylint: disable=too-few-public-methods
    """Splits a document's text into chapters based on double page break delimiters."""

    def hydrate(self, document: Document) -> None:
        """Split the document text into Chapter objects and attach them.

        Skips empty text chunks that may appear from consecutive delimiters.
        """
        text = document.get_text()
        chapters = [Chapter(text=chunk) for chunk in text.split(CHAPTER_DELIMITER) if chunk.strip()]
        document.chapters[:] = chapters
