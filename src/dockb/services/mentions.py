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
            key = " ".join(_entry_words(entry))
            owners.setdefault(key, []).append(chapter.id)
    return owners


def evaluate_chapter_tier1(  # pylint: disable=too-many-positional-arguments,too-many-arguments
    chapter_id: str,
    *,
    owner: str,
    mentions_repo: Any,
    chapter_repo: Any,
    document_repo: Any,
    cancel: threading.Event | None = None,
) -> None:
    """Evaluate a chapter's state-1 and state-4 paragraphs, tier 1.

    Writes each settled paragraph's verdicts (a mention per character, or a
    "mentions nobody" verdict) and stamps it checked. A paragraph with a
    match on an ambiguous entry is left **unstamped** — tier 2, the model,
    must judge it first — but its unambiguous verdicts are written so a
    search can already see them.

    *cancel*, when set between paragraphs, ends the pass: nothing further is
    stamped and the rollup is left for the successor run.
    """
    pending, chapter, characters, ambiguity = _gather(chapter_id, owner, mentions_repo, chapter_repo, document_repo)
    if pending is None or chapter is None or _stop_requested(cancel):
        return

    now = datetime.now(timezone.utc).isoformat()
    for paragraph_id in pending:
        if _stop_requested(cancel):
            return
        paragraph = next((p for p in chapter.paragraphs if p.id == paragraph_id), None)
        if paragraph is None:
            continue
        verdicts, waiting = _judge_paragraph(paragraph, characters, ambiguity)
        if waiting:
            # Tier 2 must judge the ambiguous evidence; the settled verdicts
            # are written without the stamp so the paragraph stays un-evaluated.
            if verdicts:
                mentions_repo.stamp(paragraph_id, verdicts, owner=owner)
        else:
            mentions_repo.stamp(paragraph_id, verdicts, owner=owner, checked_at=now)
    if _stop_requested(cancel):
        return
    _refresh_rollup(chapter_id, owner=owner, mentions_repo=mentions_repo, chapter_repo=chapter_repo, document_repo=document_repo)


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
    states = {state["id"]: state["state"] for state in mentions_repo.paragraph_states(owner, chapter_id=chapter_id)}
    pending = [state_id for state_id, state in states.items() if state in (1, 4)]
    return pending, chapter, characters, ambiguity


def _judge_paragraph(  # pylint: disable=too-many-locals,too-many-branches
    paragraph: Paragraph,
    characters: list[Chapter],
    ambiguity: dict[str, list[str]],
) -> tuple[list[dict[str, Any]], list[Chapter]]:
    """One paragraph's tier-1 verdicts, and the characters waiting on tier 2.

    The paragraph's sentences are read as token runs: at each position, the
    LONGEST name-set entry matching an adjacent run of tokens wins, and the
    defeated shorter matches (a nickname "Adams" completed by "Jael" before
    it) create no verdict for the character they would have named. When the
    winning run's length is tied between characters — a shared surname alone —
    every tied character waits on tier 2.
    """
    by_id = {character.id: character for character in characters}
    entries = _name_entries(characters, ambiguity)

    verdicts: list[dict[str, Any]] = []
    waiting: list[Chapter] = []
    matched: dict[str, bool] = {}  # character id -> pending anywhere in the paragraph?
    for sentence in paragraph.sentences:
        words: list[tuple[str, bool]] = []
        for token in sentence.tokens:
            if token.pos in (POS.PUNCT, POS.PART):
                continue
            # a hyphenated token ("Jer-bear") splits like a hyphenated entry
            for piece in token.text.lower().split("-"):
                if piece:
                    words.append((piece, token.pos == POS.PROPN))
        position = 0
        while position < len(words):
            best_length = 0
            winners: dict[str, bool] = {}
            for entry_words, character, unique in entries:
                length = len(entry_words)
                if length < best_length or position + length > len(words):
                    continue
                run = words[position : position + length]
                if [word for word, _proper in run] != list(entry_words):
                    continue
                if not run[0][1]:  # a name run starts at a proper noun
                    continue
                if length == best_length:
                    # a tie at the winning length: both characters are candidates
                    winners[character.id] = winners.get(character.id, False) or unique
                else:
                    best_length = length
                    winners = {character.id: unique}
            for character_id, unique in winners.items():
                matched[character_id] = matched.get(character_id, False) or not unique
            # the winning run consumes its tokens: a defeated shorter match
            # inside it (the "Adams" of "Jeremiah Edgar Adams") counts no more
            position += max(best_length, 1)

    for character_id, is_pending in matched.items():
        if is_pending:
            waiting.append(by_id[character_id])
        else:
            verdicts.append({"character_id": character_id, "method": "name", "confidence": 1.0})
    return verdicts, waiting


def _name_entries(characters: list[Chapter], ambiguity: dict[str, list[str]]) -> list[tuple[tuple[str, ...], Chapter, bool]]:
    """Every character's name-set entries as word tuples: (words, character, unambiguous?)."""
    entries: list[tuple[tuple[str, ...], Chapter, bool]] = []
    for character in characters:
        for entry in name_set(character):
            entry_words = _entry_words(entry)
            if entry_words:
                unique = len(ambiguity.get(" ".join(entry_words), [])) <= 1
                entries.append((tuple(entry_words), character, unique))
    return entries


def _entry_words(entry: str) -> list[str]:
    """An entry split into words, hyphenated pieces split apart, lowercased."""
    words: list[str] = []
    for word in entry.lower().split():
        words.extend(word.split("-"))
    return words


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


def evaluate_chapter_tier2(  # pylint: disable=too-many-arguments,too-many-positional-arguments,too-many-locals,too-many-branches
    chapter_id: str,
    *,
    owner: str,
    mentions_repo: Any,
    chapter_repo: Any,
    document_repo: Any,
    complete: Any = None,
    nlp: Any = None,
    no_ai: bool = False,
    cancel: threading.Event | None = None,
) -> None:
    """Evaluate a chapter's pending paragraphs (tier 2): the model judges the
    ambiguous evidence.

    The tier-1 pass leaves a paragraph un-stamped when its only evidence is
    ambiguous; this pass gathers those paragraphs' candidates, asks the model
    in one batch, and stamps each paragraph whose candidates are all settled —
    mentions as `method: "model"`, rejections as a no-mentions verdict. A
    candidate the model could not answer leaves its paragraph un-stamped for
    the next trigger to retry.

    *cancel* marks the pass superseded: checked before the batch is sent (an
    unanswered document costs nothing), and again before each paragraph's
    verdicts are stamped, so what a still-flying batch comes back with is
    discarded rather than written.
    """
    pending, chapter, characters, ambiguity = _gather(chapter_id, owner, mentions_repo, chapter_repo, document_repo)
    if pending is None or chapter is None or _stop_requested(cancel):
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
        text = _paragraph_text(paragraph)
        settled, still_waiting = _settle_by_ner(text, settled, waiting, ambiguity, nlp)
        per_paragraph[paragraph_id] = (settled, still_waiting)
        for character in still_waiting:
            candidates.append(
                {
                    "key": f"{paragraph_id}:{character.id}",
                    "sentence": text,
                    "character_title": character.title,
                    "names": name_set(character),
                }
            )

    if not candidates or _stop_requested(cancel):
        return

    if no_ai and candidates:
        logger.warning(
            "The model was needed to judge %d ambiguous mention candidate(s), "
            "but the call was prevented by the --no-ai setting; they stay un-evaluated",
            len(candidates),
        )
        return
    verdicts = judge_ambiguous(candidates, complete=complete)
    if _stamps_tier2_verdicts(per_paragraph, verdicts, mentions_repo=mentions_repo, owner=owner, cancel=cancel):
        return
    _refresh_rollup(chapter_id, owner=owner, mentions_repo=mentions_repo, chapter_repo=chapter_repo, document_repo=document_repo)


def _stamps_tier2_verdicts(
    per_paragraph: dict[str, tuple[list[dict[str, Any]], list[Chapter]]],
    verdicts: dict[str, bool | None],
    *,
    mentions_repo: Any,
    owner: str,
    cancel: threading.Event | None,
) -> bool:
    """Stamp the model's verdicts per paragraph; say whether the run was cancelled.

    Each paragraph whose candidates all settled is stamped — mentions as
    `method: "model"`, rejections as a no-mentions verdict — and one the
    model could not answer stays un-stamped for the next trigger to retry.
    A post-answer cancellation still discards the rest: the verdicts were
    computed for a state the chapter has left behind.
    """
    now = datetime.now(timezone.utc).isoformat()
    for paragraph_id, (settled, waiting) in per_paragraph.items():
        if _stop_requested(cancel):
            return True
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
                mentions_repo.stamp(paragraph_id, settled, owner=owner)
        else:
            mentions_repo.stamp(paragraph_id, settled, owner=owner, checked_at=now)
    return _stop_requested(cancel)


def _settle_by_ner(
    text: str,
    settled: list[dict[str, Any]],
    waiting: list[Chapter],
    ambiguity: dict[str, list[str]],
    nlp: Any,
) -> tuple[list[dict[str, Any]], list[Chapter]]:
    """The NER pass: a PERSON span exactly equal to one candidate's name-set
    entry — and to nobody else's — resolves that candidate deterministically.

    NER never rejects: a name the small model failed to tag falls through to
    the real judge.
    """
    person_spans = _ner_spans(nlp, text) if nlp is not None else []
    settled = list(settled)
    still_waiting: list[Chapter] = []
    for character in waiting:
        claimed = [
            span.text
            for span in person_spans
            if span.label_ == "PERSON" and _normalised(span.text) in [_normalised(entry) for entry in name_set(character)]
        ]
        if claimed and len(ambiguity.get(_normalised(claimed[0]), [])) <= 1:
            settled.append({"character_id": character.id, "method": "name", "confidence": 1.0})
        else:
            still_waiting.append(character)
    return settled, still_waiting


def _ner_spans(nlp: Any, text: str) -> list[Any]:
    """The entity spans of *text* under the pipeline's spaCy model (None-safe)."""
    try:
        return list(nlp(text).ents)
    except Exception:  # pylint: disable=broad-except
        # NER is an optimisation, never a gate: a failure falls to the model.
        logger.warning("The NER pass failed; the candidates go straight to the model", exc_info=True)
        return []


def _normalised(name: str) -> str:
    """A name's comparison key: lowercased, hyphens and possessives flattened."""
    return " ".join(word for word in name.lower().replace("'", "").replace("-", " ").split())


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


def _stop_requested(cancel: threading.Event | None) -> bool:
    """Whether *cancel* has been asked to stop (never for a None cancel)."""
    return cancel is not None and cancel.is_set()


class MentionsJob:  # pylint: disable=too-few-public-methods
    """The evaluation of one chapter's pending paragraphs.

    Carries the chapter's scope and the repositories; `run` does the work
    (tier 1, then tier 2 for what tier 1 left pending). It is a plain object
    rather than a JobQueue job: the queue a chapter save could use is not
    wired in production, and a mentions evaluation wants no ordering
    guarantees beyond "after the commit" — which the caller guarantees by
    only constructing it after the save returned. One chapter per job; a
    document-wide trigger schedules one job per chapter (the scheduler
    coalesces runs for the same chapter).

    *cancel* is the scheduler's cooperative stop signal — the job checks it
    at its own checkpoints and leaves the rest to a successor run.
    """

    def __init__(  # pylint: disable=too-many-arguments,too-many-positional-arguments
        self,
        *,
        mentions_repo: Any,
        chapter_repo: Any,
        document_repo: Any,
        owner: str,
        chapter_id: str,
        cancel: threading.Event | None = None,
    ) -> None:
        self.chapter_id = chapter_id
        self._repos = (mentions_repo, chapter_repo, document_repo)
        self._owner = owner
        self.cancel = cancel

    def run(self) -> None:
        """Evaluate every pending paragraph of the job's chapter, both tiers."""
        mentions_repo, chapter_repo, document_repo = self._repos
        _evaluate_chapter(
            self.chapter_id,
            owner=self._owner,
            mentions_repo=mentions_repo,
            chapter_repo=chapter_repo,
            document_repo=document_repo,
            cancel=self.cancel,
        )


def _evaluate_chapter(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    chapter_id: str,
    *,
    owner: str,
    mentions_repo: Any,
    chapter_repo: Any,
    document_repo: Any,
    cancel: threading.Event | None = None,
) -> None:
    """Both tiers for one chapter's pending paragraphs, then the chapter rollup.

    *cancel* is checked at the pipeline's own checkpoints — a superseded
    evaluation stops stamping and leaves the rest to its successor run.
    """
    if _stop_requested(cancel):
        return
    evaluate_chapter_tier1(
        chapter_id,
        owner=owner,
        mentions_repo=mentions_repo,
        chapter_repo=chapter_repo,
        document_repo=document_repo,
        cancel=cancel,
    )
    if _stop_requested(cancel):
        return
    evaluate_chapter_tier2(
        chapter_id,
        owner=owner,
        mentions_repo=mentions_repo,
        chapter_repo=chapter_repo,
        document_repo=document_repo,
        cancel=cancel,
    )
    if _stop_requested(cancel):
        return
    _refresh_rollup(chapter_id, owner=owner, mentions_repo=mentions_repo, chapter_repo=chapter_repo, document_repo=document_repo)


def _refresh_rollup(chapter_id: str, *, owner: str, mentions_repo: Any, chapter_repo: Any, document_repo: Any) -> None:
    """The chapter's own MENTIONS: the characters its paragraphs' valid verdicts name.

    A view, never a judgement — rebuilt from the paragraph verdicts after every
    evaluation, and marked stale by the same invalidation that marks them.
    """
    document_id = chapter_repo.find_document_id(chapter_id, owner)
    if document_id is None:
        return
    document: Document | None = document_repo.load(document_id, owner)
    if document is None:
        return
    character_titles = {chapter.id: chapter.title for chapter in document.chapters if chapter.category == "Character"}
    mentioned: set[str] = set()
    total = 0
    for state in mentions_repo.paragraph_states(owner, chapter_id=chapter_id):
        if state["state"] != 3:
            continue
        for character_id in state["mentions"]:
            if character_id in character_titles:
                total += 1
                mentioned.add(character_id)
    mentions_repo.stamp_chapter(chapter_id, sorted(mentioned), owner=owner)
    chapter_title = next((chapter.title for chapter in document.chapters if chapter.id == chapter_id), chapter_id)
    logger.info("Mentions for chapter '%s': %d", chapter_title, total)
