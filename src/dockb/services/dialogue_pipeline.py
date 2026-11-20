"""The dialogue pass that fixes quotes and stamps speakers after a chapter save."""

from __future__ import annotations

import logging
import threading
from datetime import datetime, timezone
from typing import Any

from dockb.services.dialogue import DialogueSpan, QuoteCorrection, find_dialogue, token_quote_fixes, token_spans
from dockb.services.speakers import find_speakers

logger = logging.getLogger(__name__)


def evaluate_chapter_dialogue(  # pylint: disable=too-many-arguments,too-many-positional-arguments,too-many-locals
    chapter_id: str,
    *,
    owner: str,
    chapter_repo: Any,
    sentence_repo: Any,
    cancel: threading.Event | None = None,
) -> None:
    """Run one dialogue pass over a chapter's sentences that need checking."""
    document_id = chapter_repo.find_document_id(chapter_id, owner)
    if document_id is None or (cancel is not None and cancel.is_set()):
        return
    chapter = chapter_repo.load(chapter_id, owner)
    if chapter is None:
        return

    paragraphs = [list(paragraph.sentences) for paragraph in chapter.paragraphs]
    pending = {
        (paragraph_index, sentence_index)
        for paragraph_index, paragraph in enumerate(paragraphs)
        for sentence_index, sentence in enumerate(paragraph)
        if not sentence.dialogue_checked_at
    }
    if not pending or (cancel is not None and cancel.is_set()):
        return

    texts = [[sentence.get_text() for sentence in paragraph] for paragraph in paragraphs]
    result = find_dialogue(texts)
    characters = chapter_repo.list_characters(document_id, owner)
    verdicts = find_speakers(
        paragraphs,
        result.spans,
        characters,
        chapter_repo=chapter_repo,
        document_id=document_id,
        owner=owner,
    )
    if cancel is not None and cancel.is_set():
        return

    checked_at = datetime.now(timezone.utc).isoformat()
    spans_by_sentence: dict[tuple[int, int], list[DialogueSpan]] = {}
    for span in result.spans:
        spans_by_sentence.setdefault((span.paragraph, span.sentence), []).append(span)
    corrections_by_sentence: dict[tuple[int, int], list[QuoteCorrection]] = {}
    for correction in result.corrections:
        corrections_by_sentence.setdefault((correction.paragraph, correction.sentence), []).append(correction)

    stamps: list[dict[str, Any]] = []
    for key in sorted(pending):
        paragraph_index, sentence_index = key
        sentence = paragraphs[paragraph_index][sentence_index]
        token_pairs = [(token.text, token.trailing_ws) for token in sentence.tokens]
        spans = token_spans(token_pairs, spans_by_sentence.get(key, []))
        fixes = token_quote_fixes(token_pairs, corrections_by_sentence.get(key, []))
        start_token, end_token = spans[0] if spans else (-1, -1)
        stamps.append(
            {
                "sentence_id": sentence.id,
                "is_dialogue": bool(spans),
                "start_token": start_token,
                "end_token": end_token,
                "spans": spans,
                "checked_at": checked_at,
                "tokens": [
                    {"id": token.id, "text": fixes[index][0], "trailing_ws": fixes[index][1]}
                    for index, token in enumerate(sentence.tokens)
                    if index in fixes
                ],
            }
        )

    pending_ids = {paragraphs[p][s].id for p, s in pending}
    spoken_by = [
        {
            "sentence_id": verdict.sentence_id,
            "character_id": verdict.character_id,
            "method": verdict.method,
            "confidence": verdict.confidence,
            "reference": verdict.reference,
            "stale": False,
        }
        for verdict in verdicts
        if verdict.sentence_id in pending_ids
    ]

    sentence_repo.stamp_dialogue(stamps, owner=owner)
    sentence_repo.stamp_spoken_by(spoken_by, owner=owner)
    logger.debug("Dialogue pass for chapter '%s': %d sentences, %d speakers", chapter_id, len(stamps), len(spoken_by))
