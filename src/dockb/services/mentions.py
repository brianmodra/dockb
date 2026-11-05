"""The mention pipeline's tier 1: the deterministic name-set evaluation.

A paragraph mentions a character when one of the character's **name set**
entries — first name, surname, first+surname, the full name, each nickname —
appears in it as whole words, read from the graph's `PROPN` tokens. Tier 1
settles every unambiguous case without a model call; a match on a name that
two or more of the document's characters share ("Adams" as Jael's surname and
Jeremiah's nickname) is left for tier 2, the model, to judge.

Only paragraphs in states 1 (never evaluated) and 4 (invalidated) are
evaluated; 2 and 3 carry fresh verdicts already.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from dockb.models.chapter import Chapter
from dockb.models.document import Document
from dockb.models.paragraph import Paragraph
from dockb.models.token import POS


def name_set(chapter: Chapter) -> list[str]:
    """Every string that can count as naming *chapter*'s character.

    first name, surname, first+surname, the full name (first name, middle
    names, surname joined with spaces), and each nickname — de-duplicated,
    order-preserving.
    """
    first = chapter.first_name
    surname = chapter.surname
    entries = [
        first,
        surname,
        " ".join([first, *chapter.middle_names, surname]).strip(),
        *(chapter.nicknames or []),
    ]
    seen: list[str] = []
    for entry in entries:
        entry = entry.strip()
        if entry and entry.lower() not in [seen_entry.lower() for seen_entry in seen]:
            seen.append(entry)
    return seen


def _whole_word(text: str, entry: str) -> bool:
    """Whether *entry* appears in *text* as whole words, case-insensitively."""
    found = re.search(rf"(?<!\w){re.escape(entry)}(?!\w)", text, re.IGNORECASE) is not None
    return bool(found)


def _paragraph_text(paragraph: Paragraph) -> str:
    """The paragraph's sentences joined, each token's whitespace preserved."""
    return " ".join(sentence.get_text().rstrip() for sentence in paragraph.sentences)


def _is_proper_noun(token: Any) -> bool:
    return bool(token.pos == POS.PROPN)


def _ambiguity(document: Document) -> dict[str, list[str]]:
    """Which characters' name sets contain each entry (the document's own)."""
    owners: dict[str, list[str]] = {}
    for chapter in document.chapters:
        if chapter.category != "Character":
            continue
        for entry in name_set(chapter):
            owners.setdefault(entry.lower(), []).append(chapter.id)
    return owners


def evaluate_chapter_tier1(
    chapter_id: str,
    *,
    owner: str,
    mentions_repo: Any,
    chapter_repo: Any,
    document_repo: Any,
) -> None:
    """Evaluate a chapter's state-1 and state-4 paragraphs, tier 1.

    Writes each settled paragraph's verdicts (a mention per character, or a
    "mentions nobody" verdict) and stamps it checked. A paragraph with a
    match on an ambiguous entry is left **unstamped** — tier 2, the model,
    must judge it first — but its unambiguous verdicts are written so a
    search can already see them.
    """
    pending, chapter, characters, ambiguity = _gather(chapter_id, owner, mentions_repo, chapter_repo, document_repo)
    if pending is None or chapter is None:
        return

    now = datetime.now(timezone.utc).isoformat()
    for paragraph_id in pending:
        paragraph = next((p for p in chapter.paragraphs if p.id == paragraph_id), None)
        if paragraph is None:
            continue
        verdicts, has_pending = _judge_paragraph(paragraph, characters, ambiguity)
        if has_pending:
            # Tier 2 must judge the ambiguous evidence; the settled verdicts
            # are written without the stamp so the paragraph stays un-evaluated.
            if verdicts:
                mentions_repo.stamp(paragraph_id, verdicts)
        else:
            mentions_repo.stamp(paragraph_id, verdicts, checked_at=now)


def _gather(
    chapter_id: str,
    owner: str,
    mentions_repo: Any,
    chapter_repo: Any,
    document_repo: Any,
) -> tuple[list[str] | None, Chapter | None, list[Chapter], dict[str, list[str]]]:
    """The chapter's pending paragraph ids, the chapter, the cast, and the ambiguity map."""
    document_id = chapter_repo.find_document_id(chapter_id, owner)
    if document_id is None:
        return None, None, [], {}
    document: Document | None = document_repo.load(document_id, owner)
    if document is None:
        return None, None, [], {}
    chapter = next((c for c in document.chapters if c.id == chapter_id), None)
    if chapter is None:
        return None, None, [], {}
    characters = [c for c in document.chapters if c.category == "Character"]
    if not characters:
        return None, None, [], {}
    ambiguity = _ambiguity(document)
    states = {state["id"]: state["state"] for state in mentions_repo.paragraph_states(chapter_id, owner=owner)}
    pending = [state_id for state_id, state in states.items() if state in (1, 4)]
    return pending, chapter, characters, ambiguity


def _judge_paragraph(
    paragraph: Paragraph,
    characters: list[Chapter],
    ambiguity: dict[str, list[str]],
) -> tuple[list[dict[str, Any]], bool]:
    """One paragraph's tier-1 verdicts, and whether ambiguous evidence waits on tier 2."""
    text = _paragraph_text(paragraph)
    verdicts: list[dict[str, Any]] = []
    has_pending = False
    for character in characters:
        matched_entry: str | None = None
        ambiguous = False
        for entry in name_set(character):
            if not _whole_word(text, entry):
                continue
            if not _is_proper_noun_match(paragraph, entry):
                continue
            if len(ambiguity.get(entry.lower(), [])) > 1:
                ambiguous = True
            else:
                matched_entry = entry
                break
        if matched_entry is not None:
            verdicts.append({"character_id": character.id, "method": "name", "confidence": 1.0})
        elif ambiguous:
            has_pending = True
    return verdicts, has_pending


def _is_proper_noun_match(paragraph: Paragraph, entry: str) -> bool:
    """Whether a PROPN token of *paragraph* can begin a match of *entry*.

    The entry's first word is what spaCy tagged; the rest of the entry (the
    surname after the first name, a nickname's hyphenated tail) is confirmed
    on the text by the caller.
    """
    first_word = entry.split()[0]
    for sentence in paragraph.sentences:
        for token in sentence.tokens:
            if token.pos == POS.PROPN and token.text.lower() == first_word.lower():
                return True
    return False
