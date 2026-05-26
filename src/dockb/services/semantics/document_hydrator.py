"""Document hydration service that splits document text into chapters."""

from dockb.models.chapter import Chapter
from dockb.models.document import Document

CHAPTER_DELIMITER = "\f\f"


class DocumentHydrator:
    """Splits a document's text into chapters based on double page break delimiters."""

    def hydrate(self, document: Document) -> None:
        text = document.get_text()
        chapters = [Chapter(text=chunk) for chunk in text.split(CHAPTER_DELIMITER)]
        document.chapters = chapters
