"""The MCP query tools' logic: chapter lookups and the paragraph criteria tree.

The tree is the contract: a criterion is either a leaf — a whole **word**, a
**text** substring, or a **character** (a person of the story, by id or by
name) — or an **and**/**or** node over an array of criteria. A paragraph
matches the tree when the operators say so; the and-node demands every child,
the or-node any.

Matching runs in memory over one owner-scoped document load, not a Cypher
query per node: a book is small, and the tree is the caller's, not something
the graph should evaluate.
"""

from __future__ import annotations

import re
from typing import Any

from dockb.models.chapter import Chapter
from dockb.models.document import Document
from dockb.services.chapter_json import load_chapter_payload, paragraph_payload
from dockb.services.mentions import MentionsJob, run_mentions_async

Criterion = dict[str, Any]


def evaluate_criteria(criteria: Criterion, text: str, names: list[str] | None = None) -> bool:
    """Evaluate the criteria *tree* against one paragraph's *text*.

    *names* carries the character names a character leaf may match — the
    resolved character's first name, nicknames, and first+surname pair — and
    is needed only by character leaves.
    """
    kind = criteria.get("type")
    if kind == "criteria":
        children = criteria.get("criteria") or []
        matches = (evaluate_criteria(child, text, names) for child in children)
        if criteria.get("op") == "and":
            return all(matches)
        return any(matches)
    if kind == "word":
        return re.search(rf"\b{re.escape(str(criteria.get('word', '')))}\b", text, re.IGNORECASE) is not None
    if kind == "text":
        return str(criteria.get("text", "")).lower() in text.lower()
    if kind == "character":
        wanted = names or []
        return any(_mentions_whole_word(text, candidate) for candidate in wanted)
    return False


def _mentions_whole_word(text: str, candidate: str) -> bool:
    """Whether *text* contains *candidate* as whole words (case-insensitively)."""
    if not candidate:
        return False
    return re.search(rf"\b{re.escape(candidate)}\b", text, re.IGNORECASE) is not None


def _character_names(chapter: Chapter) -> list[str]:
    """The strings a mention of this character can read as: first name, nicknames, first+surname."""
    first = chapter.first_name
    candidates = [first]
    if first and chapter.surname:
        candidates.append(first + " " + chapter.surname)
    candidates.extend(chapter.nicknames or [])
    return [name for name in candidates if name]


def _resolve_character(reference: str, document: Document, chapter_repo: Any, owner: str) -> Chapter | None:
    """The Character chapter a criterion names: by id, then by title, then by matched name."""
    by_id = next((c for c in document.chapters if c.id == reference and c.category == "Character"), None)
    if by_id is not None:
        return by_id
    by_title = next(
        (c for c in document.chapters if c.category == "Character" and c.title.lower() == reference.lower()),
        None,
    )
    if by_title is not None:
        return by_title
    match = chapter_repo.find_character_by_name(document.id, reference.split(), owner)
    if match is None:
        return None
    return next((c for c in document.chapters if c.id == match["id"]), None)


def find_paragraphs_payload(  # pylint: disable=too-many-arguments,too-many-positional-arguments,too-many-locals
    document_id: str,
    criteria: Criterion,
    *,
    chapter_repo: Any,
    document_repo: Any,
    owner: str,
    include_characters: bool = False,
    mentions_repo: Any | None = None,
) -> list[dict[str, object]]:
    """The paragraphs of *document_id* the criteria tree selects, in reading order.

    The document is loaded owner-scoped (a document another account owns is
    nobody's: the empty list). Only manuscript chapters are searched unless
    *include_characters* is set, in which case the character chapters'
    paragraphs are searched too. Every matching paragraph comes back as the
    tools' full payload — its properties, its sentences with their canonical
    text, the chapter it hangs under, and its position there.

    A character criterion is answered from the MENTIONS cache when the
    paragraph has been evaluated (states 2 and 3); a paragraph never evaluated
    or invalidated (states 1 and 4) is matched by tier 1 inline, and the full
    evaluation of the document is enqueued as the async job — so the answer
    never waits on the model, and later searches see its verdicts. When no
    mentions repository is given, the character criterion is answered by the
    inline name match alone.
    """
    document: Document | None = document_repo.load(document_id, owner)
    if document is None:
        return []

    characters = {chapter.id: _character_names(chapter) for chapter in document.chapters if chapter.category == "Character"}
    if mentions_repo is not None:
        states = {state["id"]: state for state in mentions_repo.paragraph_states(owner, document_id=document_id)}
    else:
        states = {}
    enqueue = mentions_repo is not None and _has_character_leaf(criteria)

    def resolve_node(node: Criterion, text: str, state: int, mention_targets: list[str]) -> bool:
        if node.get("type") == "character":
            reference = str(node.get("character", ""))
            names = characters.get(reference)
            if names is None:
                character = _resolve_character(reference, document, chapter_repo, owner)
                names = _character_names(character) if character is not None else []
            if state in (2, 3):
                # The verdict is in the cache: state 2 judged "mentions nobody";
                # state 3 mentions exactly the characters its valid rels name.
                resolved_id = reference if reference in characters else _resolved_character_id(reference, document, chapter_repo, owner)
                return state == 3 and resolved_id in mention_targets
            return any(_mentions_whole_word(text, candidate) for candidate in names)
        if node.get("type") == "criteria":
            children = node.get("criteria") or []
            matches = (resolve_node(child, text, state, mention_targets) for child in children)
            if node.get("op") == "and":
                return all(matches)
            return any(matches)
        return evaluate_criteria(node, text)

    found: list[dict[str, object]] = []
    for chapter in document.chapters:
        if chapter.category == "Character" and not include_characters:
            continue
        for index, paragraph in enumerate(chapter.paragraphs):
            text = "\n".join(sentence.get_text().rstrip() for sentence in paragraph.sentences)
            state = states.get(paragraph.id, {"state": 1, "mentions": []})
            if resolve_node(criteria, text, state["state"], state["mentions"]):
                found.append(paragraph_payload(paragraph, index, chapter.id, chapter_title=chapter.title))

    if enqueue and any(row["state"] in (1, 4) for row in states.values()):
        run_mentions_async(
            MentionsJob(
                document_id=document_id,
                mentions_repo=mentions_repo,
                chapter_repo=chapter_repo,
                document_repo=document_repo,
                owner=owner,
            )
        )
    return found


def _has_character_leaf(criteria: Criterion) -> bool:
    if criteria.get("type") == "character":
        return True
    return any(_has_character_leaf(child) for child in criteria.get("criteria") or [])


def _resolved_character_id(reference: str, document: Document, chapter_repo: Any, owner: str) -> str | None:
    character = _resolve_character(reference, document, chapter_repo, owner)
    return character.id if character is not None else None


def _matches_tree(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    criteria: Criterion,
    text: str,
    characters: dict[str, list[str]],
    document: Document,
    chapter_repo: Any,
    owner: str,
) -> bool:
    """Evaluate the tree for one paragraph, resolving character references first."""

    def resolve_node(node: Criterion) -> bool:
        if node.get("type") == "character":
            reference = str(node.get("character", ""))
            names = characters.get(reference)
            if names is None:
                character = _resolve_character(reference, document, chapter_repo, owner)
                names = _character_names(character) if character is not None else []
            return evaluate_criteria(node, text, names)
        if node.get("type") == "criteria":
            children = node.get("criteria") or []
            matches = (resolve_node(child) for child in children)
            if node.get("op") == "and":
                return all(matches)
            return any(matches)
        return evaluate_criteria(node, text)

    return resolve_node(criteria)


def get_chapter_payload(
    *,
    chapter_id: str | None = None,
    document_id: str | None = None,
    title: str | None = None,
    chapter_repo: Any,
    owner: str,
) -> dict[str, object] | None:
    """A chapter by id, or by title within a document — the tools' chapter shape.

    A title is only unique within a document, so a title without a document
    resolves to nothing. Returns None when the chapter is absent or *owner*
    does not own it.
    """
    resolved = chapter_id
    if resolved is None and document_id is not None and title:
        found = chapter_repo.find_id_by_title(document_id, title, owner)
        resolved = str(found) if found else None
    if resolved is None:
        return None
    return load_chapter_payload(resolved, chapter_repo=chapter_repo, owner=owner)
