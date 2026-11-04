"""The chapter-as-JSON payload the MCP tools return: paragraphs with their
properties, and sentences as properties plus their canonical text.

The shape is deliberately flat and self-describing — an LLM (or any client)
reads a chapter top to bottom without knowing the graph's storage rules. The
properties are the node's own, so whatever the schema gains rides along.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from dockb.models.chapter import Chapter
from dockb.models.paragraph import Paragraph
from dockb.models.sentence import Sentence
from dockb.services.chapter_front_matter import reconcile_pov_title

if TYPE_CHECKING:
    from dockb.repositories.chapter_repository import ChapterRepository


def sentence_payload(sentence: Sentence, index: int) -> dict[str, object]:
    """One sentence: its node properties plus its tokens rendered as plain text.

    The text is the canonical markdown line — the tokens joined by the
    whitespace each carries, the trailing whitespace of the last dropped.
    """
    return {
        "id": sentence.id,
        "index": index,
        "text": sentence.get_text().rstrip(),
    }


def paragraph_payload(paragraph: Paragraph, index: int, chapter_id: str, chapter_title: str = "") -> dict[str, object]:
    """One paragraph: its node properties, its position and chapter, and its sentences."""
    return {
        "id": paragraph.id,
        "index": index,
        "chapter_id": chapter_id,
        "chapter_title": chapter_title,
        "quote_type": paragraph.quote_type,
        "sentences": [sentence_payload(sentence, order) for order, sentence in enumerate(paragraph.sentences)],
    }


def chapter_payload(chapter: Chapter, *, chapter_id_ref: str, pov_title: str | None = None) -> dict[str, object]:
    """A chapter as JSON: identity, point of view, and its paragraphs in order.

    *pov_title* is the chapter's POV character's title already resolved by the
    caller (the id-to-title lookup is a repository concern); None or empty
    means the chapter has no point of view.
    """
    return {
        "id": chapter.id,
        "title": chapter.title,
        "act": chapter.act,
        "category": chapter.category,
        "pov": pov_title or None,
        "paragraphs": [
            paragraph_payload(paragraph, index, chapter_id_ref, chapter_title=chapter.title)
            for index, paragraph in enumerate(chapter.paragraphs)
        ],
    }


def load_chapter_payload(chapter_id: str, *, chapter_repo: ChapterRepository, owner: str) -> dict[str, object] | None:
    """Load *chapter_id* owner-scoped and render it as the tools' payload.

    The POV is answered as the character chapter's **title** (resolved from the
    stored id; empty when the chapter has none or it dangles). Returns None
    when *owner* does not own the chapter.
    """
    chapter = chapter_repo.load(chapter_id, owner)
    if chapter is None:
        return None
    document_id = chapter_repo.find_document_id(chapter_id, owner)
    pov_title = reconcile_pov_title(chapter, document_id, chapter_repo, owner) if document_id is not None else ""
    return chapter_payload(chapter, chapter_id_ref=chapter_id, pov_title=pov_title)
