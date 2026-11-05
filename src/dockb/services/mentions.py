"""The mention pipeline's tiers: deterministic names first, the model for the
ambiguous remainder.

Tier 1: a paragraph mentions a character when one of the character's **name
set** entries — first name, surname, first+surname, the full name, each
nickname — appears in it as whole words, read from the graph's `PROPN` tokens.
Tier 1 settles every unambiguous case without a model call; a match on a name
that two or more of the document's characters share ("Adams" as Jael's surname
and Jeremiah's nickname) is left for tier 2, the model, to judge.

Tier 2: the ambiguous candidates' sentences go to OpenAI in one batched prompt
(numbered sentences, JSON verdicts back). Any failure — no API key, network,
unparseable answer — is benign: the candidate stays un-evaluated and is
retried by the next trigger.

Only paragraphs in states 1 (never evaluated) and 4 (invalidated) are
evaluated; 2 and 3 carry fresh verdicts already.
"""

from __future__ import annotations

import json
import logging
import os
import re
import threading
from datetime import datetime, timezone
from typing import Any

import httpx2

from dockb.models.chapter import Chapter
from dockb.models.document import Document
from dockb.models.paragraph import Paragraph
from dockb.models.token import POS

logger = logging.getLogger(__name__)

_MENTIONS_MODEL_ENV_VAR = "DOCKB_MENTIONS_MODEL"
_DEFAULT_MODEL = "gpt-4o-mini"
_KEY_ENV_VAR = "OPENAI_API_KEY"


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
        verdicts, waiting = _judge_paragraph(paragraph, characters, ambiguity)
        if waiting:
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
) -> tuple[list[dict[str, Any]], list[Chapter]]:
    """One paragraph's tier-1 verdicts, and the characters waiting on tier 2.

    A character whose matched evidence is unambiguous lands a verdict; one
    whose only matches are names this document's other characters share is
    returned in the pending list for tier 2 to judge.
    """
    text = _paragraph_text(paragraph)
    verdicts: list[dict[str, Any]] = []
    waiting: list[Chapter] = []
    for character in characters:
        settled = False
        ambiguous = False
        for entry in name_set(character):
            if not _whole_word(text, entry):
                continue
            if not _is_proper_noun_match(paragraph, entry):
                continue
            if len(ambiguity.get(entry.lower(), [])) > 1:
                ambiguous = True
                break
            settled = True
            break
        if settled:
            verdicts.append({"character_id": character.id, "method": "name", "confidence": 1.0})
        elif ambiguous:
            waiting.append(character)
    return verdicts, waiting


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


def judge_ambiguous(candidates: list[dict[str, Any]], *, complete: Any) -> dict[str, bool | None]:
    """Ask the model to judge each ambiguous candidate; answer per candidate key.

    *candidates* is `[{key, sentence, character_title, names}]`; the prompt
    numbers them, states each candidate character's names once, and asks for
    JSON verdicts. An answer that cannot be got — a model error, an
    unparseable reply — leaves that candidate None: unresolved, not false.
    """
    if not candidates:
        return {}
    lines = [
        f"{number}. {candidate['sentence']} - possibly mentioning "
        f"\"{candidate['character_title']}\" (names: {', '.join(candidate['names'])})"
        for number, candidate in enumerate(candidates, start=1)
    ]
    prompt = "\n".join(
        [
            "For each numbered sentence, decide whether it mentions the named character",
            "(a person, not just words that happen to match). Answer with a JSON object",
            "mapping each number to true or false, and nothing else.",
            "",
            *lines,
        ]
    )
    try:
        # A failed call is a pending candidate, not a crash: the paragraph
        # stays un-evaluated and the next trigger retries it.
        answer = complete(prompt)
    except Exception:  # pylint: disable=broad-except; any failure is a pending candidate, not a crash
        logger.warning("The mention judge's model call failed; the candidates stay un-evaluated", exc_info=True)
        return {candidate["key"]: None for candidate in candidates}
    try:
        verdicts = json.loads(answer)
        if not isinstance(verdicts, dict):
            raise ValueError("not a JSON object")
    except (ValueError, TypeError):
        logger.warning("The mention judge's answer was not a JSON verdict object")
        return {candidate["key"]: None for candidate in candidates}
    out: dict[str, bool | None] = {}
    for number, candidate in enumerate(candidates, start=1):
        value = verdicts.get(str(number))
        out[candidate["key"]] = bool(value) if isinstance(value, bool) else None
    return out


def evaluate_chapter_tier2(  # pylint: disable=too-many-arguments,too-many-positional-arguments,too-many-locals
    chapter_id: str,
    *,
    owner: str,
    mentions_repo: Any,
    chapter_repo: Any,
    document_repo: Any,
    complete: Any = None,
) -> None:
    """Evaluate a chapter's pending paragraphs (tier 2): the model judges the
    ambiguous evidence.

    The tier-1 pass leaves a paragraph un-stamped when its only evidence is
    ambiguous; this pass gathers those paragraphs' candidates, asks the model
    in one batch, and stamps each paragraph whose candidates are all settled —
    mentions as `method: "model"`, rejections as a no-mentions verdict. A
    candidate the model could not answer leaves its paragraph un-stamped for
    the next trigger to retry.
    """
    pending, chapter, characters, ambiguity = _gather(chapter_id, owner, mentions_repo, chapter_repo, document_repo)
    if pending is None or chapter is None:
        return

    api_key = os.environ.get(_KEY_ENV_VAR)
    if not api_key or not api_key.strip():
        logger.warning("OPENAI_API_KEY is not set: the ambiguous mention candidates stay un-evaluated")
        return
    if complete is None:
        complete = _openai_complete

    candidates: list[dict[str, Any]] = []
    per_paragraph: dict[str, tuple[list[dict[str, Any]], list[Chapter]]] = {}
    for paragraph_id in pending:
        paragraph = next((p for p in chapter.paragraphs if p.id == paragraph_id), None)
        if paragraph is None:
            continue
        settled, waiting = _judge_paragraph(paragraph, characters, ambiguity)
        per_paragraph[paragraph_id] = (settled, waiting)
        text = _paragraph_text(paragraph)
        for character in waiting:
            candidates.append(
                {
                    "key": f"{paragraph_id}:{character.id}",
                    "sentence": text,
                    "character_title": character.title,
                    "names": name_set(character),
                }
            )

    verdicts = judge_ambiguous(candidates, complete=complete)

    now = datetime.now(timezone.utc).isoformat()
    for paragraph_id, (settled, waiting) in per_paragraph.items():
        settled = list(settled)
        unresolved = False
        for character in waiting:
            verdict = verdicts.get(f"{paragraph_id}:{character.id}")
            if verdict is True:
                settled.append({"character_id": character.id, "method": "model", "confidence": 1.0})
            elif verdict is None:
                unresolved = True
        if unresolved:
            if settled:
                mentions_repo.stamp(paragraph_id, settled)
        else:
            mentions_repo.stamp(paragraph_id, settled, checked_at=now)


def _openai_complete(prompt: str) -> str:
    """The model call behind tier 2: one chat-completion, temperature 0, JSON out."""
    key = os.environ.get(_KEY_ENV_VAR, "")
    response = httpx2.post(
        "https://api.openai.com/v1/chat/completions",
        headers={"Authorization": f"Bearer {key}"},
        json={
            "model": os.environ.get(_MENTIONS_MODEL_ENV_VAR, _DEFAULT_MODEL),
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0,
        },
        timeout=120.0,
    )
    response.raise_for_status()
    payload = response.json()
    return str(payload["choices"][0]["message"]["content"])


class MentionsJob:  # pylint: disable=too-few-public-methods
    """The evaluation of one chapter's (or one document's) pending paragraphs.

    Carries the scope and the repositories; `run` does the work (tier 1, then
    tier 2 for what tier 1 left pending). It is a plain object rather than a
    JobQueue job: the queue a chapter save could use is not wired in
    production, and a mentions evaluation wants no ordering guarantees beyond
    "after the commit" — which the caller guarantees by only constructing it
    after the save returned.
    """

    def __init__(  # pylint: disable=too-many-arguments,too-many-positional-arguments
        self,
        *,
        mentions_repo: Any,
        chapter_repo: Any,
        document_repo: Any,
        owner: str,
        chapter_id: str | None = None,
        document_id: str | None = None,
    ) -> None:
        self.chapter_id = chapter_id
        self.document_id = document_id
        self._repos = (mentions_repo, chapter_repo, document_repo)
        self._owner = owner

    def run(self) -> None:
        """Evaluate every pending paragraph in the job's scope, both tiers."""
        mentions_repo, chapter_repo, document_repo = self._repos
        if self.chapter_id is not None:
            chapter_ids: list[str] = [self.chapter_id]
        elif self.document_id is not None:
            chapter_ids = _document_chapter_ids(self.document_id, owner=self._owner, document_repo=document_repo)
        else:
            return
        for chapter_id in chapter_ids:
            _evaluate_chapter(
                chapter_id,
                owner=self._owner,
                mentions_repo=mentions_repo,
                chapter_repo=chapter_repo,
                document_repo=document_repo,
            )


def run_mentions_async(job: MentionsJob) -> None:
    """Run *job* on a one-shot daemon thread: the caller never waits on it."""
    threading.Thread(target=job.run, daemon=True).start()


def _document_chapter_ids(document_id: str, *, owner: str, document_repo: Any) -> list[str]:
    document: Document | None = document_repo.load(document_id, owner)
    if document is None:
        return []
    return [chapter.id for chapter in document.chapters]


def _evaluate_chapter(chapter_id: str, *, owner: str, mentions_repo: Any, chapter_repo: Any, document_repo: Any) -> None:
    """Both tiers for one chapter's pending paragraphs."""
    evaluate_chapter_tier1(chapter_id, owner=owner, mentions_repo=mentions_repo, chapter_repo=chapter_repo, document_repo=document_repo)
    evaluate_chapter_tier2(chapter_id, owner=owner, mentions_repo=mentions_repo, chapter_repo=chapter_repo, document_repo=document_repo)
