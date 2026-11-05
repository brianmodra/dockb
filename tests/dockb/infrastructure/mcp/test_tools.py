"""The MCP tools: mounting, the account subject, and their answers."""

from unittest.mock import MagicMock

import pytest
from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from dockb.infrastructure.mcp.auth import _account_id  # pylint: disable=protected-access
from dockb.infrastructure.mcp.tools import mount_tools
from dockb.models.base import DataState
from dockb.models.chapter import Chapter
from dockb.models.document import Document
from dockb.models.paragraph import Paragraph
from dockb.models.sentence import Sentence
from dockb.models.token import Token


def _chapter_document() -> Document:
    document = Document(id="d1", state=DataState.SYNC)
    chapter = Chapter(id="c1", title="Opening 1", state=DataState.SYNC)
    paragraph = Paragraph(id="p1", quote_type="reading", state=DataState.SYNC)
    sentence = Sentence(state=DataState.SYNC)
    for word in ("The", "murder", "was", "discovered."):
        sentence.tokens.append(Token(text=word, trailing_ws=" ", state=DataState.SYNC))
    paragraph.sentences.append(sentence)
    chapter.paragraphs.append(paragraph)
    document.chapters.append(chapter)
    return document


@pytest.fixture()
def repos():
    mentions_repo = MagicMock()
    mentions_repo.paragraph_states.return_value = []
    return_fixture = {"mentions": mentions_repo}
    chapter_repo = MagicMock()
    chapter_repo.load.return_value = None
    chapter_repo.find_document_id.return_value = "d1"
    chapter_repo.find_character_title.return_value = None
    chapter_repo.find_id_by_title.return_value = "c1"
    document_repo = MagicMock()
    document_repo.load.return_value = _chapter_document()
    return_fixture["chapter"] = chapter_repo
    return_fixture["document"] = document_repo
    return (chapter_repo, document_repo, mentions_repo)


@pytest.mark.asyncio
async def test_mounting_registers_both_tools() -> None:
    mcp = MCPServer("DockB")
    mount_tools(mcp, chapter_repo=MagicMock(), document_repo=MagicMock(), mentions_repo=MagicMock())

    names = [tool.name for tool in await mcp.list_tools()]
    assert names == ["get_chapter", "find_paragraphs"]


@pytest.mark.asyncio
@pytest.mark.asyncio
async def test_get_chapter_answers_for_the_tokens_account(repos) -> None:
    chapter_repo, document_repo, _mentions = repos
    chapter_repo.load.return_value = _chapter_document().chapters[0]
    mcp = MCPServer("DockB")
    mount_tools(mcp, chapter_repo=chapter_repo, document_repo=document_repo, mentions_repo=MagicMock())
    token = _account_id.set("acct-1")

    chapter = await mcp.call_tool("get_chapter", {"chapter_id": "c1"})

    assert chapter is not None
    chapter_repo.load.assert_called_once_with("c1", "acct-1")
    _account_id.reset(token)


@pytest.mark.asyncio
async def test_get_chapter_without_a_bound_account_is_refused(repos) -> None:
    chapter_repo, document_repo, _mentions = repos
    mcp = MCPServer("DockB")
    mount_tools(mcp, chapter_repo=chapter_repo, document_repo=document_repo, mentions_repo=MagicMock())

    with pytest.raises(ToolError, match="account"):
        await mcp.call_tool("get_chapter", {"chapter_id": "c1"})


@pytest.mark.asyncio
async def test_get_chapter_resolves_a_title_within_a_document(repos) -> None:
    chapter_repo, document_repo, _mentions = repos
    chapter_repo.load.return_value = _chapter_document().chapters[0]
    mcp = MCPServer("DockB")
    mount_tools(mcp, chapter_repo=chapter_repo, document_repo=document_repo, mentions_repo=MagicMock())
    token = _account_id.set("acct-1")

    chapter = await mcp.call_tool("get_chapter", {"document_id": "d1", "title": "Opening 1"})

    chapter_repo.find_id_by_title.assert_called_once_with("d1", "Opening 1", "acct-1")
    assert chapter is not None
    _account_id.reset(token)


@pytest.mark.asyncio
async def test_find_paragraphs_answers_the_selection(repos) -> None:
    chapter_repo, document_repo, mentions_repo = repos
    chapter_repo.load.return_value = _chapter_document().chapters[0]
    mcp = MCPServer("DockB")
    mount_tools(mcp, chapter_repo=chapter_repo, document_repo=document_repo, mentions_repo=mentions_repo)
    token = _account_id.set("acct-1")

    found = await mcp.call_tool("find_paragraphs", {"document_id": "d1", "criteria": {"type": "word", "word": "murder"}})

    assert found is not None
    assert found.is_error is False
    paragraphs = found.structured_content["paragraphs"]
    assert len(paragraphs) == 1
    assert paragraphs[0]["id"] == "p1"
    assert paragraphs[0]["chapter_id"] == "c1"

    await mcp.call_tool(
        "find_paragraphs",
        {"document_id": "d1", "criteria": {"type": "word", "word": "murder"}, "include_characters": True},
    )
    # the flag reached the search: the second call loaded the document again
    # with it, and neither call raised (validated parameters)
    assert document_repo.load.call_count == 2
    # and the mentions cache was consulted for the character criterion
    assert mentions_repo.paragraph_states.called
    _account_id.reset(token)
