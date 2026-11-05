"""The MENTIONS cache's repository: the four paragraph states and their writes.

A paragraph's mention verdicts live as `MENTIONS` relationships to the
character chapters they name, plus a `mentions_checked_at` stamp that
distinguishes "checked and none" from "never asked". The states the pipeline
asks for:

1. never evaluated — no stamp;
2. evaluated, no mentions — stamp set, no MENTIONS;
3. valid MENTIONS — stamp set, MENTIONS with `stale` absent or false;
4. invalidated — stamp set, MENTIONS with `stale: true` (kept until re-judged).

Invalidation marks rather than deletes: a stale relationship keeps its old
verdict visible until the evaluator replaces it.
"""

from __future__ import annotations

from typing import Any

from neo4j import Session

_CHAPTER_STATES_CYPHER = """
MATCH (p:Paragraph)-[pr:PART_OF]->(ch:Chapter {id: $chapter_id})-[:PART_OF]->(d:Document {owner: $owner})
OPTIONAL MATCH (p)-[m:MENTIONS]->(target:Chapter)
WITH p, collect({character_id: target.id, stale: coalesce(m.stale, false)}) AS mentions
RETURN
  p.id AS id,
  p.mentions_checked_at AS checked_at,
  mentions
"""

_DOCUMENT_STATES_CYPHER = """
MATCH (p:Paragraph)-[pr:PART_OF]->(ch:Chapter)-[:PART_OF]->(d:Document {id: $document_id, owner: $owner})
OPTIONAL MATCH (p)-[m:MENTIONS]->(target:Chapter)
WITH p, collect({character_id: target.id, stale: coalesce(m.stale, false)}) AS mentions
RETURN
  p.id AS id,
  p.mentions_checked_at AS checked_at,
  mentions
"""

_CHAPTER_MARK_STALE_CYPHER = """
MATCH (p:Paragraph)-[pr:PART_OF]->(ch:Chapter {id: $chapter_id})-[:PART_OF]->(d:Document {owner: $owner})
OPTIONAL MATCH (p)-[m:MENTIONS]->()
WITH p, collect(m) AS rels
FOREACH (m IN rels | SET m.stale = true)
WITH p, rels
WHERE size(rels) = 0 AND p.mentions_checked_at IS NOT NULL
SET p.mentions_checked_at = null
"""

_DOCUMENT_MARK_STALE_CYPHER = """
MATCH (p:Paragraph)-[pr:PART_OF]->(ch:Chapter)-[:PART_OF]->(d:Document {id: $document_id, owner: $owner})
OPTIONAL MATCH (p)-[m:MENTIONS]->()
WITH p, collect(m) AS rels
FOREACH (m IN rels | SET m.stale = true)
WITH p, rels
WHERE size(rels) = 0 AND p.mentions_checked_at IS NOT NULL
SET p.mentions_checked_at = null
"""

_STAMP_CYPHER = """
MATCH (p:Paragraph {id: $paragraph_id})-[:PART_OF]->(ch:Chapter)-[:PART_OF]->(d:Document {owner: $owner})
OPTIONAL MATCH (p)-[m:MENTIONS]->()
DELETE m
WITH p
UNWIND $verdicts AS verdict
MATCH (c:Chapter {id: verdict.character_id, category: 'Character'})
CREATE (p)-[:MENTIONS {method: verdict.method, confidence: verdict.confidence}]->(c)
WITH DISTINCT p
SET p.mentions_checked_at = $checked_at
"""


class MentionsRepository:
    """Reads and writes the mention verdicts; not a model repository.

    The mentions have no model of their own — they are the cache between a
    paragraph and a character chapter — so this repository is plain Cypher
    over the session, shaped around the four states.
    """

    def __init__(self, session: Session) -> None:
        self._session = session

    def paragraph_states(
        self,
        owner: str,
        *,
        chapter_id: str | None = None,
        document_id: str | None = None,
    ) -> list[dict[str, int | str]]:
        """Every paragraph of the scope with its state number (1-4).

        Exactly one of *chapter_id* / *document_id* names the scope; a state-1
        paragraph is one with no stamp (its un-stamped MENTIONS, when present,
        are a tier-1 pass whose tier-2 judgement is still pending).
        """
        if chapter_id is not None:
            cypher = _CHAPTER_STATES_CYPHER
            params: dict[str, str | None] = {"chapter_id": chapter_id, "owner": owner}
        else:
            cypher = _DOCUMENT_STATES_CYPHER
            params = {"document_id": document_id, "owner": owner}
        records = list(self._session.run(cypher, params))
        states: list[dict[str, int | str]] = []
        for record in records:
            checked = record.get("checked_at")
            mentions = record.get("mentions") or []
            if checked is None:
                state = 1
            elif not mentions:
                state = 2
            elif any(mention.get("stale") for mention in mentions):
                state = 4
            else:
                state = 3
            states.append({"id": str(record["id"]), "state": state})
        return states

    def stamp(
        self,
        paragraph_id: str,
        verdicts: list[dict[str, Any]],
        *,
        checked_at: str,
    ) -> None:
        """Replace *paragraph_id*'s verdicts wholesale and stamp it evaluated.

        *verdicts* is `[{character_id, method, confidence}]` — an empty list is
        a "mentions nobody" verdict, which is what turns the paragraph into
        state 2.
        """
        self._session.run(
            _STAMP_CYPHER,
            {"paragraph_id": paragraph_id, "verdicts": verdicts, "checked_at": checked_at},
        )

    def mark_stale(self, owner: str, *, chapter_id: str | None = None, document_id: str | None = None) -> None:
        """Invalidate every verdict in the scope (a chapter, or a whole document).

        Relationships become `stale: true` (state 4, kept until re-judged);
        paragraphs that had judged nobody (state 2) lose their stamp and return
        to state 1 — the name set changed, so their "no mentions" verdict is
        stale too, and only the evaluator can tell what the new names match.
        """
        if chapter_id is not None:
            cypher = _CHAPTER_MARK_STALE_CYPHER
            params: dict[str, str | None] = {"chapter_id": chapter_id, "owner": owner}
        else:
            cypher = _DOCUMENT_MARK_STALE_CYPHER
            params = {"document_id": document_id, "owner": owner}
        self._session.run(cypher, params)
