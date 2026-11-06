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
WITH p, pr.index AS index, collect({character_id: target.id, stale: coalesce(m.stale, false)}) AS mentions
RETURN
  p.id AS id,
  index,
  p.mentions_checked_at AS checked_at,
  mentions
"""

_DOCUMENT_STATES_CYPHER = """
MATCH (p:Paragraph)-[pr:PART_OF]->(ch:Chapter)-[:PART_OF]->(d:Document {id: $document_id, owner: $owner})
OPTIONAL MATCH (p)-[m:MENTIONS]->(target:Chapter)
WITH p, pr.index AS index, collect({character_id: target.id, stale: coalesce(m.stale, false)}) AS mentions
RETURN
  p.id AS id,
  index,
  p.mentions_checked_at AS checked_at,
  mentions
"""

_CHAPTER_MARK_STALE_CYPHER = """
MATCH (ch:Chapter {id: $chapter_id})-[:PART_OF]->(d:Document {owner: $owner})
OPTIONAL MATCH (ch)-[cm:MENTIONS]->()
WITH ch, collect(cm) AS chapter_rels
FOREACH (cm IN chapter_rels | SET cm.stale = true)
MATCH (p:Paragraph)-[pr:PART_OF]->(ch)
OPTIONAL MATCH (p)-[m:MENTIONS]->()
WITH p, collect(m) AS rels
FOREACH (m IN rels | SET m.stale = true)
WITH p, rels
WHERE size(rels) = 0 AND p.mentions_checked_at IS NOT NULL
SET p.mentions_checked_at = null
"""

_DOCUMENT_MARK_STALE_CYPHER = """
MATCH (ch:Chapter)-[:PART_OF]->(d:Document {id: $document_id, owner: $owner})
OPTIONAL MATCH (ch)-[cm:MENTIONS]->()
WITH ch, collect(cm) AS chapter_rels
FOREACH (cm IN chapter_rels | SET cm.stale = true)
MATCH (p:Paragraph)-[pr:PART_OF]->(ch)
OPTIONAL MATCH (p)-[m:MENTIONS]->()
WITH p, collect(m) AS rels
FOREACH (m IN rels | SET m.stale = true)
WITH p, rels
WHERE size(rels) = 0 AND p.mentions_checked_at IS NOT NULL
SET p.mentions_checked_at = null
"""

_CHAPTER_RESET_CYPHER = """
MATCH (p:Paragraph)-[pr:PART_OF]->(ch:Chapter {id: $chapter_id})-[:PART_OF]->(d:Document {owner: $owner})
OPTIONAL MATCH (p)-[m:MENTIONS]->()
DELETE m
WITH DISTINCT p
SET p.mentions_checked_at = null
"""

_DOCUMENT_RESET_CYPHER = """
MATCH (p:Paragraph)-[pr:PART_OF]->(ch:Chapter)-[:PART_OF]->(d:Document {id: $document_id, owner: $owner})
OPTIONAL MATCH (p)-[m:MENTIONS]->()
DELETE m
WITH DISTINCT p
SET p.mentions_checked_at = null
"""

_CHAPTER_STAMP_CYPHER = """
MATCH (ch:Chapter {id: $chapter_id})-[:PART_OF]->(d:Document {owner: $owner})
OPTIONAL MATCH (ch)-[m:MENTIONS]->()
DELETE m
WITH ch
UNWIND $character_ids AS character_id
MATCH (c:Chapter {id: character_id, category: 'Character'})
CREATE (ch)-[:MENTIONS {method: "rollup", confidence: 1.0}]->(c)
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
        states: list[dict[str, Any]] = []
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
            states.append(
                {
                    "id": str(record["id"]),
                    "state": state,
                    "index": record.get("index") or 0,
                    # the characters the valid verdicts name (empty for states 1/2/4)
                    "mentions": [str(m["character_id"]) for m in mentions if not m.get("stale")] if state == 3 else [],
                }
            )
        return states

    def stamp(
        self,
        paragraph_id: str,
        verdicts: list[dict[str, Any]],
        *,
        owner: str,
        checked_at: str | None = None,
    ) -> None:
        """Replace *paragraph_id*'s verdicts wholesale and stamp it evaluated.

        *verdicts* is `[{character_id, method, confidence}]` — an empty list is
        a "mentions nobody" verdict, which is what turns the paragraph into
        state 2. Every write is scoped to *owner* the way every read is. A
        *checked_at* left off is a tier-1 partial write: verdicts become
        visible while the paragraph stays un-stamped for tier 2 to finish.
        """
        self._session.run(
            _STAMP_CYPHER,
            {
                "paragraph_id": paragraph_id,
                "verdicts": verdicts,
                "owner": owner,
                "checked_at": checked_at,
            },
        )

    def reset(self, owner: str, *, chapter_id: str | None = None, document_id: str | None = None) -> None:
        """Forget every verdict in the scope: no stamp, no MENTIONS (all state 1).

        The sweep's ``--full`` uses it: a re-evaluation from nothing, the old
        verdicts not even kept as stale.
        """
        if chapter_id is not None:
            cypher = _CHAPTER_RESET_CYPHER
            params: dict[str, str | None] = {"chapter_id": chapter_id, "owner": owner}
        else:
            cypher = _DOCUMENT_RESET_CYPHER
            params = {"document_id": document_id, "owner": owner}
        self._session.run(cypher, params)

    def stamp_chapter(self, chapter_id: str, character_ids: list[str], *, owner: str) -> None:
        """Refresh the chapter's own MENTIONS rollup from its paragraphs' valid verdicts.

        The rollup is a view, never a judgement: the caller derives
        *character_ids* from the paragraph verdicts it just stamped, and this
        replaces the chapter's relationships wholesale.
        """
        self._session.run(
            _CHAPTER_STAMP_CYPHER,
            {"chapter_id": chapter_id, "character_ids": character_ids, "owner": owner},
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
