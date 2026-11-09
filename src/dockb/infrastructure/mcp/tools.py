"""The MCP manuscript tools: read a chapter, or find the paragraphs a criteria
tree selects.

Both tools answer for the account the bearer token was minted for — the
account arrives with the request (the bearer gate binds it), and every read is
scoped to that account's manuscripts, exactly as an editor session's are. A
token with no bound account can name no books, so the tools refuse it rather
than answer an empty world.
"""

from __future__ import annotations

import json
import logging
from typing import Annotated, Any, Literal

from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from pydantic import BaseModel, Field

from dockb.infrastructure.mcp.auth import get_account_id
from dockb.repositories.chapter_repository import ChapterRepository
from dockb.repositories.paragraph_search_repository import ParagraphSearchRepository
from dockb.services.mcp_queries import find_paragraphs_payload, get_chapter_payload, get_character_name_payload

logger = logging.getLogger(__name__)

_RESPONSE_LOG_LIMIT = 2000


class WordCriterion(BaseModel):
    """A leaf that matches when the paragraph contains the word as a whole word, case-insensitively."""

    type: Literal["word"]
    word: str = Field(description="The word to match as a whole word, case-insensitively.")


class TextCriterion(BaseModel):
    """A leaf that matches when the paragraph contains the text as a substring, case-insensitively."""

    type: Literal["text"]
    text: str = Field(description="The text to match as a substring, case-insensitively. Prefer a word leaf when matching a single word.")


class CharacterCriterion(BaseModel):
    """A leaf that matches when the paragraph mentions a person of the story.

    Proper names go here, not in word leaves: the character is matched as the
    person — by character-chapter id, chapter title, or name — so surname
    mentions and nicknames find them too.
    """

    type: Literal["character"]
    character: str = Field(description="A person of the story, by character-chapter id, chapter title, or proper name.")


class CriteriaGroup(BaseModel):
    """A node that combines its children: `op` "and" matches when every child
    matches, "or" when any child does."""

    type: Literal["criteria"]
    op: Literal["and", "or"] = Field(description='"and" demands every child match; "or" any one of them.')
    criteria: list[CriteriaTree] = Field(description="The children this group combines.")


CriteriaTree = Annotated[
    WordCriterion | TextCriterion | CharacterCriterion | CriteriaGroup,
    Field(discriminator="type"),
]

CriteriaGroup.model_rebuild()


def _logged(value: Any) -> str:
    """Compact JSON for the log line, with oversized answers truncated."""
    text = json.dumps(value, default=str)
    if len(text) <= _RESPONSE_LOG_LIMIT:
        return text
    return f"{text[:_RESPONSE_LOG_LIMIT]} … ({len(text)} bytes, truncated)"


def mount_tools(
    mcp: MCPServer,
    *,
    chapter_repo: ChapterRepository,
    search_repo: ParagraphSearchRepository,
) -> None:
    """Register the manuscript tools on *mcp*."""

    def _account() -> str:
        account = get_account_id()
        if not account:
            raise ToolError("this token has no account bound to it; the tools read one account's books")
        return account

    def get_chapter(
        chapter_id: str | None = None,
        document_id: str | None = None,
        title: str | None = None,
        start_index: int | None = None,
        end_index: int | None = None,
    ) -> dict[str, Any]:
        """A chapter as paragraphs: by chapter id, or by title within a document.

        Each paragraph carries its properties (id, quote type), its position,
        and its sentences — each sentence its properties and its text as the
        canonical markdown line. Optional *start_index* and *end_index*
        (0-based inclusive paragraph positions) return only that slice of
        paragraphs while keeping each paragraph's chapter-wide ``index``.
        Unknown id, or a title without a document (or that names no chapter of
        the account's), is an error.
        """
        account = _account()
        logger.info(
            "MCP get_chapter <- %s",
            _logged(
                {
                    "chapter_id": chapter_id,
                    "document_id": document_id,
                    "title": title,
                    "start_index": start_index,
                    "end_index": end_index,
                }
            ),
        )
        payload = get_chapter_payload(
            chapter_id=chapter_id,
            document_id=document_id,
            title=title,
            start_index=start_index,
            end_index=end_index,
            chapter_repo=chapter_repo,
            owner=account,
        )
        if payload is None:
            raise ToolError("no such chapter for this account")
        logger.info("MCP get_chapter -> %s", _logged(payload))
        return payload

    def find_paragraphs(
        document_id: str,
        criteria: CriteriaTree,
        include_characters: bool = False,
    ) -> dict[str, list[dict[str, Any]]]:
        """The paragraphs of one document a criteria tree selects.

        The tree is a *CriteriaTree*: leaves — `{"type": "word", "word":
        "murder"}` (whole word), `{"type": "text", "text": "..."}` (substring),
        or `{"type": "character", "character": "Karakas"}` (a person of the
        story, proper names included) — over `{"type": "criteria", "op":
        "and"|"or", "criteria": [...]}` groups. The and-group demands every
        child; the or-group any. Each matching paragraph carries the chapter id
        it belongs to, that chapter's `chapter_index` (its position in the
        document), and the paragraph's own `index` (its position within the
        chapter); matches come in reading order (chapter_index, then index). It
        also carries its full text and its sentences, each carrying its 0-based
        index within the paragraph — and
        "matched_sentence_indices", the positions of the sentences whose own
        text the tree's word and text leaves select. Character leaves judge
        paragraphs, not sentences, so a tree of them alone marks nothing and
        the paragraph is what a reader is shown.
        """
        account = _account()
        tree = criteria.model_dump()
        logger.info(
            "MCP find_paragraphs <- %s",
            _logged({"document_id": document_id, "criteria": tree, "include_characters": include_characters}),
        )
        found = find_paragraphs_payload(
            document_id,
            tree,
            search_repo=search_repo,
            chapter_repo=chapter_repo,
            owner=account,
            include_characters=include_characters,
        )
        if found is None:
            raise ToolError("no such document for this account")
        # A bare top-level array is not a valid structured output root (the JSON
        # schema the protocol requires wants an object), so the paragraphs ride
        # in a one-key object.
        answer = {"paragraphs": found}
        logger.info("MCP find_paragraphs -> %s", _logged(answer))
        return answer

    def get_character_name(document_id: str, character: str) -> dict[str, Any]:
        """The names one character of one document is known by.

        *character* is a character-chapter id, a chapter title, or a proper
        name — the same reference a `find_paragraphs` character leaf takes. The
        answer carries the character's `id` and chapter `title`, then the name
        parts a reader sees: `first_name`, `middle_names`, `surname`, and
        `nicknames`. An unknown document, or a reference that names no
        character of it, is an error.
        """
        account = _account()
        logger.info(
            "MCP get_character_name <- %s",
            _logged({"document_id": document_id, "character": character}),
        )
        payload = get_character_name_payload(
            document_id,
            character,
            search_repo=search_repo,
            chapter_repo=chapter_repo,
            owner=account,
        )
        if payload is None:
            raise ToolError("no such document or character for this account")
        logger.info("MCP get_character_name -> %s", _logged(payload))
        return payload

    mcp.add_tool(
        get_chapter,
        name="get_chapter",
        description=(
            "One chapter of one of this account's books: its paragraphs, each with its "
            "properties and its sentences' text as written in the markdown. Pass optional "
            "0-based inclusive start_index and end_index to read a window of paragraphs "
            "rather than the whole chapter."
        ),
    )
    mcp.add_tool(
        get_character_name,
        name="get_character_name",
        description=(
            "The names one character of one of this account's documents is known by: "
            "first_name, middle_names, surname, and nicknames, plus the character's id and "
            "chapter title. Pass document_id and the same character reference a find_paragraphs "
            "character leaf takes (character-chapter id, chapter title, or proper name). Call it "
            "for every character you put in a find_paragraphs character leaf, so you know all "
            "the ways that person is named."
        ),
    )
    mcp.add_tool(
        find_paragraphs,
        name="find_paragraphs",
        description=(
            "Find paragraphs of one document by a nested criteria tree; answers {paragraphs: [...]}, "
            "in reading order, every match carrying its chapter id, chapter_index (the chapter's "
            "position in the document), index (its position within the chapter), full text, its "
            "sentences (each with its 0-based index within the paragraph), and "
            "matched_sentence_indices - the "
            "positions of the sentences whose own text the word and text leaves select (empty "
            "when the tree has only character leaves, so highlight the paragraph). Manuscript "
            "chapters only, "
            'unless include_characters is true. The leaves: {"type": "word", "word": ...} (whole '
            'word), {"type": "text", "text": ...} (substring), and {"type": "character", '
            '"character": ...} — proper names of the story\'s people go in a character leaf, never in '
            "a word leaf. Before putting a person in a character leaf, call get_character_name for "
            "that person so you know all the ways they are named. A single word goes in a word "
            "leaf — use a text leaf only for phrases and "
            'fragments of several words. Combine leaves with {"type": "criteria", "op": "and"|"or", '
            '"criteria": [...]}, where "and" demands every child and "or" any. A match only shares '
            "the searched words and names: it is a candidate, not proof that the paragraph answers "
            "the question, so read the returned text before relying on it. For example, an "
            '"and" over a character, another character, and a word returns every paragraph that '
            "mentions both people and the word somewhere."
        ),
    )
