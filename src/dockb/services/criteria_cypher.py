"""Compiles a criteria tree into a Cypher boolean expression plus its parameters.

The expression is evaluated per paragraph by the search query
(``ParagraphSearchRepository.match_paragraphs``), which binds the free
variables — ``text`` (the paragraph's canonical text, sentences joined by
newline), ``checked`` (the mentions-evaluation stamp), ``valid`` (the character
ids its MENTIONS verdicts name), and ``hasStale`` (whether a stale verdict
survives). Every value the tree carries travels as a numbered parameter, so
nothing the caller wrote is interpolated into the query text.

The semantics mirror the tier-1 inline evaluation exactly: a ``word`` leaf is
a case-insensitive whole-word match, a ``text`` leaf a case-insensitive
substring, and a ``character`` leaf answers from the mentions cache when the
paragraph was evaluated (states 2 and 3) and by whole-word name matching
otherwise (states 1 and 4).
"""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any

Criterion = dict[str, Any]
Resolver = Callable[[str], tuple[str, list[str]] | None]

# Case-insensitive, Unicode-aware whole-word matching for Java's regex engine
# (the ``=~`` operator): ``i`` widens case folding, ``U`` widens ``\b``'s word
# characters, and ``s`` lets the surrounding ``.*`` span the newlines a
# paragraph's sentences are joined by.
_WORD_FLAGS = "(?isuU)"


def compile_criteria(criteria: Criterion, resolve: Resolver) -> tuple[str, dict[str, Any]]:
    """Compile *criteria* into a Cypher ``WHERE`` expression and its parameters.

    *resolve* turns a character reference (character-chapter id, title, or
    name) into the chapter's id and the names a mention of them can read as,
    or ``None`` when nobody in the story answers to it. An unresolvable
    character, an unknown leaf type, and an empty or-node all compile to
    ``false``; an empty and-node to ``true`` — each exactly what the inline
    evaluator answers for the same tree.
    """
    params: dict[str, Any] = {}
    return _compile(criteria, resolve, params), params


def _compile(node: Criterion, resolve: Resolver, params: dict[str, Any]) -> str:
    kind = node.get("type") if isinstance(node, dict) else None
    if kind == "criteria":
        children = node.get("criteria") or []
        if not children:
            return "true" if node.get("op") == "and" else "false"
        joiner = " AND " if node.get("op") == "and" else " OR "
        return "(" + joiner.join(_compile(child, resolve, params) for child in children) + ")"
    return _compile_leaf(node, kind, resolve, params)


def _compile_leaf(node: Criterion, kind: str | None, resolve: Resolver, params: dict[str, Any]) -> str:
    if kind == "word":
        name = _next_param(params)
        params[name] = _whole_word_pattern(str(node.get("word", "")))
        return f"(text =~ ${name})"
    if kind == "text":
        name = _next_param(params)
        params[name] = str(node.get("text", "")).lower()
        return f"(toLower(text) CONTAINS ${name})"
    if kind == "character":
        resolved = resolve(str(node.get("character", "")))
        if resolved is None:
            return "false"
        character_id, names = resolved
        id_param = _next_param(params)
        params[id_param] = character_id
        names_param = _next_param(params)
        params[names_param] = [_whole_word_pattern(name) for name in names]
        cache_branch = f"checked IS NOT NULL AND NOT hasStale AND ${id_param} IN valid"
        inline_branch = f"any(n IN ${names_param} WHERE text =~ n)"
        return f"(({cache_branch}) OR ({inline_branch}))"
    return "false"


def _whole_word_pattern(value: str) -> str:
    # Neo4j's =~ full-matches the whole string (Java's String.matches), so the
    # whole-word match carries the paragraph's remainder around itself
    return _WORD_FLAGS + ".*\\b" + re.escape(value) + "\\b.*"


def _next_param(params: dict[str, Any]) -> str:
    return f"p{len(params)}"
