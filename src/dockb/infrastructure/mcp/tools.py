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
from typing import Any

from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from dockb.infrastructure.mcp.auth import get_account_id
from dockb.repositories.chapter_repository import ChapterRepository
from dockb.repositories.document_repository import DocumentRepository
from dockb.services.mcp_queries import find_paragraphs_payload, get_chapter_payload

logger = logging.getLogger(__name__)

_RESPONSE_LOG_LIMIT = 2000


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
    document_repo: DocumentRepository,
    mentions_repo: Any | None = None,
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
    ) -> dict[str, Any]:
        """A chapter as paragraphs: by chapter id, or by title within a document.

        Each paragraph carries its properties (id, quote type), its position,
        and its sentences — each sentence its properties and its text as the
        canonical markdown line. Unknown id, or a title without a document (or
        that names no chapter of the account's), is an error.
        """
        account = _account()
        logger.info("MCP get_chapter <- %s", _logged({"chapter_id": chapter_id, "document_id": document_id, "title": title}))
        payload = get_chapter_payload(
            chapter_id=chapter_id,
            document_id=document_id,
            title=title,
            chapter_repo=chapter_repo,
            owner=account,
        )
        if payload is None:
            raise ToolError("no such chapter for this account")
        logger.info("MCP get_chapter -> %s", _logged(payload))
        return payload

    def find_paragraphs(
        document_id: str,
        criteria: dict[str, Any],
        include_characters: bool = False,
    ) -> dict[str, list[dict[str, Any]]]:
        """The paragraphs of one document a criteria tree selects.

        The tree: `{"type": "criteria", "op": "and"|"or", "criteria": [...]}`
        nodes over leaves — `{"type": "word", "word": "murder"}` (whole word),
        `{"type": "text", "text": "..."}` (substring), or
        `{"type": "character", "character": "Karakas"}` (a person of the story:
        by character-chapter id, title, or name matched as the POV field
        matches them). The and-node demands every child; the or-node any. Each
        matching paragraph carries the chapter id it belongs to and its
        position there, with its full text.
        """
        account = _account()
        logger.info(
            "MCP find_paragraphs <- %s",
            _logged({"document_id": document_id, "criteria": criteria, "include_characters": include_characters}),
        )
        found = find_paragraphs_payload(
            document_id,
            criteria,
            chapter_repo=chapter_repo,
            document_repo=document_repo,
            owner=account,
            include_characters=include_characters,
            mentions_repo=mentions_repo,
        )
        # A bare top-level array is not a valid structured output root (the JSON
        # schema the protocol requires wants an object), so the paragraphs ride
        # in a one-key object.
        answer = {"paragraphs": found}
        logger.info("MCP find_paragraphs -> %s", _logged(answer))
        return answer

    mcp.add_tool(
        get_chapter,
        name="get_chapter",
        description=(
            "One chapter of one of this account's books: its paragraphs, each with its "
            "properties and its sentences' text as written in the markdown."
        ),
    )
    mcp.add_tool(
        find_paragraphs,
        name="find_paragraphs",
        description=(
            "Find paragraphs of one document by a nested criteria tree over words, text "
            "substrings, and story characters; answers {paragraphs: [...]}, every match "
            "carrying its chapter id, position, and full text. Manuscript chapters only, "
            "unless include_characters is true."
        ),
    )
