"""The MCP manuscript tools: read a chapter, or find the paragraphs a criteria
tree selects.

Both tools answer for the account the bearer token was minted for — the
account arrives with the request (the bearer gate binds it), and every read is
scoped to that account's manuscripts, exactly as an editor session's are. A
token with no bound account can name no books, so the tools refuse it rather
than answer an empty world.
"""

from __future__ import annotations

from typing import Any

from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from dockb.infrastructure.mcp.auth import get_account_id
from dockb.repositories.chapter_repository import ChapterRepository
from dockb.repositories.document_repository import DocumentRepository
from dockb.services.mcp_queries import find_paragraphs_payload, get_chapter_payload


def mount_tools(
    mcp: MCPServer,
    *,
    chapter_repo: ChapterRepository,
    document_repo: DocumentRepository,
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
        payload = get_chapter_payload(
            chapter_id=chapter_id,
            document_id=document_id,
            title=title,
            chapter_repo=chapter_repo,
            owner=account,
        )
        if payload is None:
            raise ToolError("no such chapter for this account")
        return payload

    def find_paragraphs(document_id: str, criteria: dict[str, Any]) -> list[dict[str, Any]]:
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
        return find_paragraphs_payload(
            document_id,
            criteria,
            chapter_repo=chapter_repo,
            document_repo=document_repo,
            owner=account,
        )

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
            "substrings, and story characters; every match carries its chapter id and position."
        ),
    )
