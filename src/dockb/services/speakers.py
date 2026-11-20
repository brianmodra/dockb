"""Speaker attribution for dialogue spans.

Each dialogue group gets one speaker, inferred from a speech verb and the
proper name or pronoun nearest to it. Names are resolved against the
document's Character chapters; pronouns are resolved by the characters'
``gender`` field. When no single character can be named, the speaker points at
the sentinel chapter ``unresolved`` and keeps the raw reference on the edge.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from dockb.models.chapter import Chapter
from dockb.models.sentence import Sentence
from dockb.models.token import POS, Token
from dockb.services.dialogue import DialogueSpan

UNRESOLVED_ID = "unresolved"

SPEECH_VERBS = frozenset(
    {
        "add",
        "answer",
        "argue",
        "ask",
        "call",
        "comment",
        "continue",
        "cry",
        "declare",
        "exclaim",
        "insist",
        "murmur",
        "mutter",
        "observe",
        "reply",
        "repeat",
        "respond",
        "say",
        "shout",
        "sigh",
        "snap",
        "state",
        "tell",
        "whisper",
        "yell",
    }
)

_FEMALE_PRONOUNS = frozenset({"she", "her", "hers", "herself"})
_MALE_PRONOUNS = frozenset({"he", "him", "his", "himself"})


@dataclass(frozen=True)
class SpeakerVerdict:
    """The speaker resolved for one sentence of dialogue."""

    sentence_id: str
    group: int
    reference: str
    character_id: str
    method: str
    confidence: float


def find_speakers(  # pylint: disable=too-many-arguments,too-many-locals
    paragraphs: Sequence[Sequence[Sentence]],
    spans: Sequence[DialogueSpan],
    characters: Sequence[Chapter],
    *,
    chapter_repo: Any,
    document_id: str,
    owner: str,
) -> list[SpeakerVerdict]:
    """Resolve one speaker per sentence in each dialogue group."""
    if not spans:
        return []

    flat: list[tuple[int, int, int, Token]] = []
    for paragraph_index, paragraph in enumerate(paragraphs):
        for sentence_index, sentence in enumerate(paragraph):
            for token_index, token in enumerate(sentence.tokens):
                flat.append((paragraph_index, sentence_index, token_index, token))

    positioned = _dialogue_tokens(paragraphs, spans)
    inside = {position for positions in positioned.values() for position in positions}
    position_of = {key: position for position, key in enumerate((p, s, t) for p, s, t, _ in flat)}
    groups: dict[int, list[DialogueSpan]] = {}
    for span in spans:
        groups.setdefault(span.group, []).append(span)

    verdicts: list[SpeakerVerdict] = []
    for group, group_spans in sorted(groups.items()):
        anchors = [position_of[position] for span in group_spans for position in positioned[span]]
        attribution = _find_attribution(flat, inside, anchors)
        reference, kind = attribution if attribution else ("", "")
        character_id, method, confidence = _resolve(
            reference, kind, characters, chapter_repo=chapter_repo, document_id=document_id, owner=owner
        )
        for paragraph_index, sentence_index in dict.fromkeys((span.paragraph, span.sentence) for span in group_spans):
            verdicts.append(
                SpeakerVerdict(
                    sentence_id=paragraphs[paragraph_index][sentence_index].id,
                    group=group,
                    reference=reference,
                    character_id=character_id,
                    method=method,
                    confidence=confidence,
                )
            )
    return verdicts


def _dialogue_tokens(
    paragraphs: Sequence[Sequence[Sentence]],
    spans: Sequence[DialogueSpan],
) -> dict[DialogueSpan, set[tuple[int, int, int]]]:
    """The token positions whose text falls inside each dialogue span."""
    positioned: dict[DialogueSpan, set[tuple[int, int, int]]] = {}
    for span in spans:
        sentence = paragraphs[span.paragraph][span.sentence]
        tokens: set[tuple[int, int, int]] = set()
        position = 0
        for token_index, token in enumerate(sentence.tokens):
            end = position + len(token.text)
            if span.start < end and span.end > position:
                tokens.add((span.paragraph, span.sentence, token_index))
            position += len(token.text) + len(token.trailing_ws)
        positioned[span] = tokens
    return positioned


def _find_attribution(
    flat: Sequence[tuple[int, int, int, Token]],
    inside: set[tuple[int, int, int]],
    anchors: Sequence[int],
) -> tuple[str, str] | None:
    """The nearest proper name or pronoun beside the group's speech verb."""
    if not anchors:
        return None
    verbs = [
        position
        for position, (paragraph, sentence, token_index, token) in enumerate(flat)
        if (paragraph, sentence, token_index) not in inside and token.pos == POS.VERB and token.lemma.casefold() in SPEECH_VERBS
    ]
    if not verbs:
        return None

    def verb_score(position: int) -> tuple[int, int, int]:
        distance, after = min((abs(position - anchor), 0 if position > anchor else 1) for anchor in anchors)
        return distance, after, position

    verb = min(verbs, key=verb_score)
    if min(abs(verb - anchor) for anchor in anchors) > 6:
        return None
    return _nearest_candidate(flat, inside, verb)


def _nearest_candidate(
    flat: Sequence[tuple[int, int, int, Token]],
    inside: set[tuple[int, int, int]],
    verb_position: int,
) -> tuple[str, str] | None:
    """Search outwards from a speech verb for an attribution token."""
    for distance in range(1, 6):
        for position in (verb_position - distance, verb_position + distance):
            if not 0 <= position < len(flat):
                continue
            paragraph, sentence, token_index, token = flat[position]
            if (paragraph, sentence, token_index) in inside:
                continue
            if token.pos == POS.PRON:
                return token.text, "pronoun"
            if token.pos == POS.PROPN:
                return _proper_name(flat, inside, position), "name"
    return None


def _proper_name(
    flat: Sequence[tuple[int, int, int, Token]],
    inside: set[tuple[int, int, int]],
    position: int,
) -> str:
    """Collect adjacent PROPN tokens around *position* into one name."""
    paragraph, sentence, _, _ = flat[position]
    words = [flat[position][3].text]
    for candidate_position in range(position - 1, -1, -1):
        candidate_paragraph, candidate_sentence, candidate_index, token = flat[candidate_position]
        if (candidate_paragraph, candidate_sentence) != (paragraph, sentence) or token.pos != POS.PROPN:
            break
        if (candidate_paragraph, candidate_sentence, candidate_index) in inside:
            break
        words.insert(0, token.text)
    for candidate_position in range(position + 1, len(flat)):
        candidate_paragraph, candidate_sentence, candidate_index, token = flat[candidate_position]
        if (candidate_paragraph, candidate_sentence) != (paragraph, sentence) or token.pos != POS.PROPN:
            break
        if (candidate_paragraph, candidate_sentence, candidate_index) in inside:
            break
        words.append(token.text)
    return " ".join(words)


def _resolve(  # pylint: disable=too-many-arguments
    reference: str,
    kind: str,
    characters: Sequence[Chapter],
    *,
    chapter_repo: Any,
    document_id: str,
    owner: str,
) -> tuple[str, str, float]:
    """Map a raw attribution to a character id, falling back to the sentinel."""
    if not reference:
        return UNRESOLVED_ID, "unresolved", 0.0

    if kind == "name":
        words = reference.split()
        found = chapter_repo.find_character_by_name(document_id, [word.lower() for word in words], owner)
        if found and found.get("id"):
            return str(found["id"]), "name", 1.0
        return UNRESOLVED_ID, "unresolved", 0.0

    gender: str | None = None
    if reference.casefold() in _FEMALE_PRONOUNS:
        gender = "female"
    elif reference.casefold() in _MALE_PRONOUNS:
        gender = "male"
    if gender is not None:
        matches = [chapter for chapter in characters if chapter.category == "Character" and chapter.gender == gender]
        if len(matches) == 1:
            return matches[0].id, "gender", 0.8
    return UNRESOLVED_ID, "unresolved", 0.0
