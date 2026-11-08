"""The MCP tools: mounting, the account subject, and their answers."""

from typing import Any
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


class _StubSearchRepo:
    """The search repository: rows to return, and the calls they answered."""

    def __init__(self, rows: list[dict[str, Any]] | None = None, exists: bool = True) -> None:
        self.rows = rows if rows is not None else []
        self.exists = exists
        self.calls: list[dict[str, Any]] = []

    def document_exists(self, document_id: str, owner: str) -> bool:  # pylint: disable=unused-argument
        return self.exists

    def character_directory(self, document_id: str, owner: str) -> list[dict[str, object]]:  # pylint: disable=unused-argument
        return []

    def match_paragraphs(  # pylint: disable=unused-argument
        self,
        document_id: str,
        owner: str,
        *,
        compiled: tuple[str, dict[str, Any]],
        include_characters: bool,
    ) -> list[dict[str, object]]:
        self.calls.append({"where": compiled[0], "params": compiled[1], "include_characters": include_characters})
        return self.rows


def _murder_row() -> dict[str, Any]:
    return {
        "id": "p1",
        "quote_type": "reading",
        "index": 0,
        "chapter_id": "c1",
        "chapter_title": "Opening 1",
        "chapter_index": 4,
        "sentences": [{"id": "s1", "text": "The murder was discovered."}],
    }


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
    return_fixture = {"search": _StubSearchRepo()}
    chapter_repo = MagicMock()
    chapter_repo.load.return_value = None
    chapter_repo.find_document_id.return_value = "d1"
    chapter_repo.find_character_title.return_value = None
    chapter_repo.find_id_by_title.return_value = "c1"
    return_fixture["chapter"] = chapter_repo
    return (chapter_repo, return_fixture["search"])


def _mount(repos, search_repo) -> MCPServer:
    chapter_repo, _ = repos
    mcp = MCPServer("DockB")
    mount_tools(
        mcp,
        chapter_repo=chapter_repo,
        search_repo=search_repo,
    )
    return mcp


@pytest.mark.asyncio
async def test_mounting_registers_both_tools() -> None:
    mcp = MCPServer("DockB")
    mount_tools(
        mcp,
        chapter_repo=MagicMock(),
        search_repo=_StubSearchRepo(),
    )

    names = [tool.name for tool in await mcp.list_tools()]
    assert names == ["get_chapter", "find_paragraphs"]


@pytest.mark.asyncio
async def test_find_paragraphs_schema_describes_the_criteria_tree() -> None:
    """The caller sees the leaf shapes, the and/or group, and each required key."""
    mcp = MCPServer("DockB")
    mount_tools(
        mcp,
        chapter_repo=MagicMock(),
        search_repo=_StubSearchRepo(),
    )

    tools = {tool.name: tool for tool in await mcp.list_tools()}
    criteria = tools["find_paragraphs"].input_schema["properties"]["criteria"]
    defs = tools["find_paragraphs"].input_schema["$defs"]

    mapping = criteria["discriminator"]["mapping"]
    assert set(mapping) == {"word", "text", "character", "criteria"}

    word_def = defs[mapping["word"].rsplit("/", 1)[-1]]
    assert set(word_def["required"]) == {"type", "word"}

    text_def = defs[mapping["text"].rsplit("/", 1)[-1]]
    assert set(text_def["required"]) == {"type", "text"}

    character_def = defs[mapping["character"].rsplit("/", 1)[-1]]
    assert set(character_def["required"]) == {"type", "character"}

    group_def = defs[mapping["criteria"].rsplit("/", 1)[-1]]
    assert set(group_def["required"]) == {"type", "op", "criteria"}
    assert group_def["properties"]["op"]["enum"] == ["and", "or"]
    assert group_def["properties"]["criteria"]["type"] == "array"

    # and the description steers a single-word search away from the text leaf
    description = tools["find_paragraphs"].description
    assert "single word" in description
    # a match shares words and names; the description must not give a worked
    # example that reads as "this match is the paragraph where the answer is"
    assert "finds out" not in description
    assert "candidate" in description


@pytest.mark.asyncio
async def test_find_paragraphs_description_states_the_reading_order() -> None:
    """The caller is told how to compare matches: chapter position, then paragraph position."""
    mcp = MCPServer("DockB")
    mount_tools(
        mcp,
        chapter_repo=MagicMock(),
        search_repo=_StubSearchRepo(),
    )

    tools = {tool.name: tool for tool in await mcp.list_tools()}
    description = tools["find_paragraphs"].description

    assert "reading order" in description
    assert "chapter_index" in description


@pytest.mark.asyncio
async def test_find_paragraphs_refuses_a_criteria_outside_the_tree(repos) -> None:
    """A shape with no leaf behind it is an error the caller can read and correct."""
    mcp = _mount(repos, _StubSearchRepo())
    token = _account_id.set("acct-1")

    with pytest.raises(ToolError, match="criteria"):
        await mcp.call_tool("find_paragraphs", {"document_id": "d1", "criteria": {"words": ["murdered"]}})
    _account_id.reset(token)


@pytest.mark.asyncio
async def test_find_paragraphs_answers_a_nested_criteria_tree(repos) -> None:
    """The tree reaches the database compiled: groups nest, leaves become parameters."""
    _chapter, search_repo = repos
    mcp = _mount(repos, search_repo)
    token = _account_id.set("acct-1")

    found = await mcp.call_tool(
        "find_paragraphs",
        {
            "document_id": "d1",
            "criteria": {
                "type": "criteria",
                "op": "and",
                "criteria": [
                    {"type": "text", "text": "murder"},
                    {"type": "word", "word": "discovered"},
                ],
            },
        },
    )
    assert found.is_error is False
    assert search_repo.calls[0]["where"] == "((toLower(text) CONTAINS $p0) AND (text =~ $p1))"

    either = await mcp.call_tool(
        "find_paragraphs",
        {
            "document_id": "d1",
            "criteria": {
                "type": "criteria",
                "op": "or",
                "criteria": [
                    {"type": "word", "word": "zebra"},
                    {"type": "word", "word": "discovered"},
                ],
            },
        },
    )
    assert either.is_error is False
    assert search_repo.calls[1]["where"] == "((text =~ $p0) OR (text =~ $p1))"
    _account_id.reset(token)


@pytest.mark.asyncio
async def test_find_paragraphs_refuses_an_unknown_document(repos) -> None:
    """A guessed document id is an error the caller can read, not a silent empty answer."""
    mcp = _mount(repos, _StubSearchRepo(exists=False))
    token = _account_id.set("acct-1")

    with pytest.raises(ToolError, match="no such document"):
        await mcp.call_tool("find_paragraphs", {"document_id": "jeremiah", "criteria": {"type": "word", "word": "murder"}})
    _account_id.reset(token)


@pytest.mark.asyncio
async def test_each_tool_call_and_its_answer_are_logged(repos, caplog) -> None:
    _chapter, search_repo = repos
    chapter_repo = repos[0]
    chapter_repo.load.return_value = _chapter_document().chapters[0]
    search_repo.rows = [_murder_row()]
    mcp = _mount(repos, search_repo)
    token = _account_id.set("acct-1")

    with caplog.at_level("INFO", logger="dockb.infrastructure.mcp.tools"):
        await mcp.call_tool("get_chapter", {"chapter_id": "c1"})
        await mcp.call_tool("find_paragraphs", {"document_id": "d1", "criteria": {"type": "word", "word": "murder"}})

    messages = [record.getMessage() for record in caplog.records]
    assert any("get_chapter" in message and "c1" in message for message in messages)
    assert any("find_paragraphs" in message and "murder" in message for message in messages)
    assert any("->" in message for message in messages), "the answer must be logged too"
    _account_id.reset(token)


@pytest.mark.asyncio
async def test_get_chapter_answers_for_the_tokens_account(repos) -> None:
    chapter_repo, _search = repos
    chapter_repo.load.return_value = _chapter_document().chapters[0]
    mcp = _mount(repos, _StubSearchRepo())
    token = _account_id.set("acct-1")

    chapter = await mcp.call_tool("get_chapter", {"chapter_id": "c1"})

    assert chapter is not None
    chapter_repo.load.assert_called_once_with("c1", "acct-1")
    _account_id.reset(token)


@pytest.mark.asyncio
async def test_get_chapter_without_a_bound_account_is_refused(repos) -> None:
    mcp = _mount(repos, _StubSearchRepo())

    with pytest.raises(ToolError, match="account"):
        await mcp.call_tool("get_chapter", {"chapter_id": "c1"})


@pytest.mark.asyncio
async def test_get_chapter_resolves_a_title_within_a_document(repos) -> None:
    chapter_repo, _search = repos
    chapter_repo.load.return_value = _chapter_document().chapters[0]
    mcp = _mount(repos, _StubSearchRepo())
    token = _account_id.set("acct-1")

    chapter = await mcp.call_tool("get_chapter", {"document_id": "d1", "title": "Opening 1"})

    chapter_repo.find_id_by_title.assert_called_once_with("d1", "Opening 1", "acct-1")
    assert chapter is not None
    _account_id.reset(token)


@pytest.mark.asyncio
async def test_find_paragraphs_answers_the_selection(repos) -> None:
    _chapter, search_repo = repos
    chapter_repo = repos[0]
    chapter_repo.load.return_value = _chapter_document().chapters[0]
    search_repo.rows = [_murder_row()]
    mcp = _mount(repos, search_repo)
    token = _account_id.set("acct-1")

    found = await mcp.call_tool("find_paragraphs", {"document_id": "d1", "criteria": {"type": "word", "word": "murder"}})

    assert found is not None
    assert found.is_error is False
    paragraphs = found.structured_content["paragraphs"]
    assert len(paragraphs) == 1
    assert paragraphs[0]["id"] == "p1"
    assert paragraphs[0]["chapter_id"] == "c1"
    assert paragraphs[0]["chapter_index"] == 4

    await mcp.call_tool(
        "find_paragraphs",
        {"document_id": "d1", "criteria": {"type": "word", "word": "murder"}, "include_characters": True},
    )
    # the flag reached the search: the second call searched with it, and neither
    # call raised (validated parameters)
    assert [call["include_characters"] for call in search_repo.calls] == [False, True]
    _account_id.reset(token)
