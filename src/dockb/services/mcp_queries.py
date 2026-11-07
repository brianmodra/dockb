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
from collections.abc import Callable
from typing import Any

from dockb.services.chapter_json import load_chapter_payload
from dockb.services.criteria_cypher import compile_criteria
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


def find_paragraphs_payload(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    document_id: str,
    criteria: Criterion,
    *,
    search_repo: Any,
    chapter_repo: Any,
    document_repo: Any,
    owner: str,
    include_characters: bool = False,
    mentions_repo: Any | None = None,
) -> list[dict[str, object]] | None:
    """The paragraphs of *document_id* the criteria tree selects, in reading order.

    The matching happens in the database: the tree compiles to a Cypher
    expression over each paragraph's reconstructed text and its mention state
    (``criteria_cypher.compile_criteria``), and ``search_repo`` answers only
    the paragraphs it selects — the manuscript is never materialized here. An
    unknown or other-account document is ``None`` — nobody's — while a known
    one with no matches is the empty list, so the tool boundary can tell the
    caller its id was wrong. Character chapters are searched only when
    *include_characters* is set.

    A character criterion is answered in the same query: from the MENTIONS
    cache where the paragraph was evaluated (states 2 and 3), and by tier-1
    inline name matching otherwise (states 1 and 4). When the document still
    has unevaluated paragraphs and the tree reads a character leaf, the full
    evaluation is enqueued as the async job — the answer never waits on the
    model, and later searches see its verdicts.
    """
    if not search_repo.document_exists(document_id, owner):
        return None
    directory = search_repo.character_directory(document_id, owner)

    def resolve(reference: str) -> tuple[str, list[str]] | None:
        """The character-chapter id and names a reference answers to, or None."""
        row = next((entry for entry in directory if entry["id"] == reference), None)
        if row is None:
            wanted = reference.lower()
            row = next((entry for entry in directory if entry["title"].lower() == wanted), None)
        if row is None:
            match = chapter_repo.find_character_by_name(document_id, reference.split(), owner)
            row = next((entry for entry in directory if match is not None and entry["id"] == match["id"]), None)
        if row is None:
            return None
        first = row["first_name"]
        names = [first]
        if first and row["surname"]:
            names.append(first + " " + row["surname"])
        names.extend(row["nicknames"] or [])
        return str(row["id"]), [name for name in names if name]

    where, params = compile_criteria(criteria, resolve)
    rows = search_repo.match_paragraphs(
        document_id,
        owner,
        compiled=(where, params),
        include_characters=include_characters,
    )

    search_answer = [_row_payload(row, criteria, resolve) for row in rows]

    states: dict[str, dict[str, Any]] = {}
    if mentions_repo is not None and _has_character_leaf(criteria):
        states = {state["id"]: state for state in mentions_repo.paragraph_states(owner, document_id=document_id)}
        if any(row["state"] in (1, 4) for row in states.values()):
            # the job runs on a daemon thread sharing this request's session;
            # it is spawned only when the tool asks the session for no more,
            # because two threads on one session corrupt the connection.
            run_mentions_async(
                MentionsJob(
                    document_id=document_id,
                    mentions_repo=mentions_repo,
                    chapter_repo=chapter_repo,
                    document_repo=document_repo,
                    owner=owner,
                )
            )
    return search_answer


def _row_payload(
    row: dict[str, Any],
    criteria: Criterion,
    resolve: Callable[[str], tuple[str, list[str]] | None],
) -> dict[str, object]:
    """One search row as the tools' paragraph payload, its sentences in order.

    The sentences the criteria tree selects all by themselves are marked — the
    model can name their ids in a highlight button, and hand the reader the
    exact sentence instead of a paragraph to hunt through. An "and" spanning
    sentences marks nothing: each condition matching a different sentence
    cannot be located, so the whole paragraph is the honest answer.
    """
    return {
        "id": row["id"],
        "index": row["index"],
        "chapter_id": row["chapter_id"],
        "chapter_title": row["chapter_title"],
        "quote_type": row["quote_type"],
        "sentences": [{"id": sentence["id"], "index": order, "text": sentence["text"]} for order, sentence in enumerate(row["sentences"])],
        "matched_sentence_ids": _marked_sentence_ids(criteria, row["sentences"], resolve),
    }


def _marked_sentence_ids(
    criteria: Criterion,
    sentences: list[dict[str, Any]],
    resolve: Callable[[str], tuple[str, list[str]] | None],
) -> list[str]:
    """The id of every sentence whose own text the criteria tree selects."""
    names: dict[str, list[str]] = {}

    def skim(reference: str) -> list[str]:
        """The spellings a character's name may take, reference included.

        The directory answers first names and pairs, and the reference the
        caller used — the model's term for the person — is often the wording
        the prose repeats, so it counts as its own spelling.
        """
        if reference not in names:
            answer = resolve(reference)
            resolved = answer[1] if answer is not None else []
            names[reference] = [*(candidate for candidate in resolved if candidate), reference]
        return names[reference]

    return [sentence["id"] for sentence in sentences if _selects_sentence(criteria, str(sentence["text"]), skim)]


def _selects_sentence(
    criterion: Criterion,
    text: str,
    skim: Callable[[str], list[str] | None],
) -> bool:
    """Whether one sentence's own text satisfies the criteria tree.

    A character leaf is answered by proper-name occurrence here — the MENTIONS
    cache is paragraph-wide, so it cannot tell which sentence the person was in.
    """
    kind = criterion.get("type")
    if kind == "criteria":
        children = criterion.get("criteria") or []
        matched = [_selects_sentence(child, text, skim) for child in children]
        if criterion.get("op") == "and":
            return all(matched)
        return any(matched)
    if kind == "word":
        return _mentions_whole_word(text, str(criterion.get("word", "")))
    if kind == "text":
        return str(criterion.get("text", "")).lower() in text.lower()
    if kind == "character":
        names = skim(str(criterion.get("character", ""))) or []
        return any(_mentions_whole_word(text, name) for name in names)
    return False


def _has_character_leaf(criteria: Criterion) -> bool:
    if criteria.get("type") == "character":
        return True
    return any(_has_character_leaf(child) for child in criteria.get("criteria") or [])


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
