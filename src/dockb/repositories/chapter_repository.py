"""Repository for persisting Chapter models to Neo4j."""

import logging
from typing import Any

from dockb.infrastructure.neo4j.base import BaseRepository
from dockb.models.base import DataState
from dockb.models.chapter import Chapter
from dockb.models.paragraph import Paragraph
from dockb.models.sentence import Sentence
from dockb.models.token import POS, Token, Type

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Write Cypher
# ---------------------------------------------------------------------------

_PARAGRAPH_UNWIND_CYPHER = """
WITH c
UNWIND $paragraphs AS p
MERGE (para:Paragraph {id: p.id})
MERGE (para)-[r:PART_OF]->(c)
SET r.index = p.index
"""

_NEW_CYPHER = f"""
MATCH (d:Document {{id: $document_id, owner: $owner}})
MERGE (c:Chapter {{id: $chapter_id}})
SET c.title = $title, c.act = $act, c.category = $category, c.title_key = toLower($title), c.document_id = $document_id
SET c.first_name = $first_name, c.surname = $surname, c.middle_names = $middle_names,
    c.nicknames = $nicknames, c.age = $age, c.location = $location, c.pov = $pov
MERGE (c)-[rc:PART_OF]->(d)
SET rc.index = $index
WITH d, c
OPTIONAL MATCH (other:Chapter)-[er:PART_OF]->(d)
WHERE other.id <> c.id AND er.index >= $index
WITH c, collect(er) AS later_rels
FOREACH (e IN later_rels | SET e.index = e.index + 1)
{_PARAGRAPH_UNWIND_CYPHER}
"""

_CHANGED_CYPHER = f"""
MATCH (d:Document {{id: $document_id, owner: $owner}})
MERGE (c:Chapter {{id: $chapter_id}})
SET c.title = $title, c.act = $act, c.category = $category, c.title_key = toLower($title), c.document_id = $document_id
SET c.first_name = $first_name, c.surname = $surname, c.middle_names = $middle_names,
    c.nicknames = $nicknames, c.age = $age, c.location = $location, c.pov = $pov
MERGE (c)-[:PART_OF]->(d)
{_PARAGRAPH_UNWIND_CYPHER}
WITH c, COLLECT(p.id) AS keep_ids
OPTIONAL MATCH (c)<-[r:PART_OF]-(orphan:Paragraph)
WHERE NOT orphan.id IN keep_ids
DETACH DELETE orphan
"""

_DELETE_CYPHER = """
MATCH (c:Chapter {id: $chapter_id})-[:PART_OF]->(:Document {owner: $owner})
OPTIONAL MATCH (p:Paragraph)-[:PART_OF]->(c)
OPTIONAL MATCH (s:Sentence)-[:PART_OF]->(p)
OPTIONAL MATCH (t:Token)-[:PART_OF]->(s)
DETACH DELETE t, s, p, c
"""

_REORDER_CYPHER = """
UNWIND $entries AS entry
MATCH (d:Document {id: $document_id, owner: $owner})<-[r:PART_OF]-(c:Chapter {id: entry.id})
SET r.index = entry.index
"""

_FIND_CHARACTER_ID_BY_TITLE_CYPHER = """
MATCH (c:Chapter {title_key: toLower($title), category: 'Character'})-[r:PART_OF]->(d:Document {id: $document_id, owner: $owner})
RETURN c.id AS id
LIMIT 1
"""

_FIND_CHARACTER_TITLE_CYPHER = """
MATCH (c:Chapter {id: $pov_id, category: 'Character'})-[r:PART_OF]->(d:Document {id: $document_id, owner: $owner})
RETURN c.title AS title
LIMIT 1
"""

_RETITLE_CYPHER = """
UNWIND $entries AS entry
MATCH (d:Document {id: $document_id, owner: $owner})<-[r:PART_OF]-(c:Chapter {id: entry.id})
SET c.title = entry.title, c.title_key = toLower(entry.title)
"""

_CLEAR_TITLE_KEYS_CYPHER = """
UNWIND $entries AS entry
MATCH (d:Document {id: $document_id, owner: $owner})<-[r:PART_OF]-(c:Chapter {id: entry.id})
SET c.title_key = c.id
"""

# ---------------------------------------------------------------------------
# Read Cypher
# ---------------------------------------------------------------------------

_LIST_BY_DOCUMENT_CYPHER = """
MATCH (c:Chapter)-[r:PART_OF]->(d:Document {id: $document_id, owner: $owner})
RETURN c.id AS id, c.title AS title, c.act AS act, c.category AS category, r.index AS index
ORDER BY r.index
"""

_FIND_DOCUMENT_CYPHER = """
MATCH (c:Chapter {id: $chapter_id})-[:PART_OF]->(d:Document {owner: $owner})
RETURN d.id AS document_id
"""

_LOAD_CYPHER = """
MATCH (c:Chapter {id: $chapter_id})-[:PART_OF]->(d:Document {owner: $owner})
OPTIONAL MATCH (p:Paragraph)-[rp:PART_OF]->(c)
OPTIONAL MATCH (s:Sentence)-[rs:PART_OF]->(p)
OPTIONAL MATCH (t:Token)-[rt:PART_OF]->(s)
RETURN
  c.id AS chapter_id, c.title AS chapter_title, c.act AS chapter_act, c.category AS chapter_category,
  c.first_name AS chapter_first_name, c.surname AS chapter_surname, c.middle_names AS chapter_middle_names,
  c.nicknames AS chapter_nicknames, c.age AS chapter_age, c.location AS chapter_location, c.pov AS chapter_pov,
  p.id AS paragraph_id, rp.index AS paragraph_index, p.quote_type AS paragraph_quote_type,
  s.id AS sentence_id, rs.index AS sentence_index,
  t.id AS token_id, rt.index AS token_index,
  t.text AS token_text, t.type AS token_type,
  t.trailing_ws AS token_trailing_ws, t.pos AS token_pos,
  t.lemma AS token_lemma, t.is_digit AS token_is_digit,
  t.like_num AS token_like_num, t.is_alpha AS token_is_alpha,
  t.is_stop AS token_is_stop
ORDER BY paragraph_index, sentence_index, token_index
"""


class ChapterRepository(BaseRepository[Chapter]):
    """Persists Chapter models to Neo4j."""

    @property
    def _new_cypher(self) -> str:
        return _NEW_CYPHER

    @property
    def _changed_cypher(self) -> str:
        return _CHANGED_CYPHER

    @property
    def _delete_cypher(self) -> str:
        return _DELETE_CYPHER

    def _build_params(self, model: Chapter, **parent_ids: str) -> dict[str, Any]:
        return {
            "document_id": parent_ids["document_id"],
            "owner": parent_ids["owner"],
            "chapter_id": model.id,
            "title": model.title,
            "act": model.act,
            "category": model.category,
            "index": int(parent_ids.get("index", "0")),
            "first_name": model.first_name,
            "surname": model.surname,
            "middle_names": list(model.middle_names),
            "nicknames": list(model.nicknames),
            "age": model.age,
            "location": model.location,
            "pov": model.pov,
            "paragraphs": [{"id": p.id, "index": i} for i, p in enumerate(model.paragraphs)],
        }

    def list_by_document(self, document_id: str, owner: str) -> list[dict[str, str | int]]:
        """Return ``[{id, title, act, category, index}]`` summaries for chapters of *document_id*.

        A document *owner* does not own yields the same empty list as one with no
        chapters, so its existence is not confirmable from here.
        """
        records = list(self._session.run(_LIST_BY_DOCUMENT_CYPHER, {"document_id": document_id, "owner": owner}))
        return [
            {
                "id": r["id"],
                "title": r.get("title") or "",
                "act": r.get("act") or "",
                "category": r.get("category") or "Chapter",
                "index": r.get("index") or 0,
            }
            for r in records
        ]

    def find_document_id(self, chapter_id: str, owner: str) -> str | None:
        """Return the owning document's id, or None when the chapter is orphaned or not owned.

        Scoped like every other read here: a chapter belonging to another account
        resolves to no document, which is what stops its file being written under the
        wrong account's tree.
        """
        records = list(self._session.run(_FIND_DOCUMENT_CYPHER, {"chapter_id": chapter_id, "owner": owner}))
        if not records:
            return None
        return str(records[0].get("document_id")) if records[0].get("document_id") is not None else None

    def reorder(self, document_id: str, ordered_ids: list[str], owner: str) -> None:
        """Rewrite the chapters' PART_OF `index` to match their position in *ordered_ids*."""
        entries = [{"id": chapter_id, "index": i} for i, chapter_id in enumerate(ordered_ids)]
        self._session.run(_REORDER_CYPHER, {"document_id": document_id, "owner": owner, "entries": entries})

    def find_character_id_by_title(self, document_id: str, title: str, owner: str) -> str | None:
        """Return the id of *document_id*'s Character chapter titled *title*, or None.

        The title matches case-insensitively through ``title_key``. Scoped to
        the same document, so a POV can only ever name a character of its own book.
        """
        records = list(
            self._session.run(
                _FIND_CHARACTER_ID_BY_TITLE_CYPHER,
                {"document_id": document_id, "title": title, "owner": owner},
            )
        )
        if not records:
            return None
        return str(records[0].get("id")) if records[0].get("id") is not None else None

    def find_character_title(self, document_id: str, pov_id: str, owner: str) -> str | None:
        """Return *pov_id*'s Character chapter title within *document_id*, or None when it dangles.

        A pov id pointing at a chapter of another document, a manuscript chapter,
        or nothing at all all read the same: unresolvable.
        """
        records = list(
            self._session.run(
                _FIND_CHARACTER_TITLE_CYPHER,
                {"document_id": document_id, "pov_id": pov_id, "owner": owner},
            )
        )
        if not records:
            return None
        return str(records[0].get("title")) if records[0].get("title") is not None else None

    def retitle(self, document_id: str, entries: list[dict[str, str]], owner: str) -> None:
        """Rewrite the chapters' `title`/`title_key` to their entry's title, in one transaction.

        The renumbered chapters' `title_key` is first cleared to their id — unique
        per chapter — before the final titles land, because the
        (``document_id``, ``title_key``) uniqueness constraint is checked the
        moment a row lands: renumbering through each other (``Opening 5`` →
        ``Opening 2`` while ``Opening 2`` → ``Opening 3``) would otherwise
        transiently collide with the chapter that has not moved yet. Both
        statements run in one transaction, so a failure leaves every title as
        it was.
        """
        params = {"document_id": document_id, "owner": owner, "entries": entries}
        with self._session.begin_transaction() as tx:
            tx.run(_CLEAR_TITLE_KEYS_CYPHER, params)
            tx.run(_RETITLE_CYPHER, params)

    def load(self, chapter_id: str, owner: str) -> Chapter | None:  # pylint: disable=too-many-locals
        """Load a Chapter and its full child hierarchy from Neo4j.

        Returns None when no chapter with *chapter_id* hangs under a document *owner*
        owns — the same answer as when no such chapter exists at all, so a chapter id
        belonging to another account is not confirmable.
        """
        logger.debug("Load Chapter %s", chapter_id)
        records = list(self._session.run(_LOAD_CYPHER, {"chapter_id": chapter_id, "owner": owner}))
        if not records:
            return None

        first = records[0]
        if first.get("chapter_id") is None:
            return None

        chapter = Chapter(
            id=first["chapter_id"],
            title=first.get("chapter_title") or "",
            act=first.get("chapter_act") or "",
            category=first.get("chapter_category") or "Chapter",
            first_name=first.get("chapter_first_name") or "",
            surname=first.get("chapter_surname") or "",
            middle_names=list(first.get("chapter_middle_names") or []),
            nicknames=list(first.get("chapter_nicknames") or []),
            age=first.get("chapter_age"),
            location=first.get("chapter_location") or "",
            pov=first.get("chapter_pov") or "",
            state=DataState.SYNC,
        )

        seen_paragraphs: set[str] = set()
        seen_sentences: set[str] = set()
        current_paragraph: Paragraph | None = None
        current_sentence: Sentence | None = None

        for rec in records:
            p_id = rec.get("paragraph_id")
            if p_id is not None and p_id not in seen_paragraphs:
                seen_paragraphs.add(p_id)
                current_paragraph = Paragraph(id=p_id, state=DataState.SYNC, quote_type=rec.get("paragraph_quote_type") or "")
                chapter.paragraphs.append(current_paragraph)

            s_id = rec.get("sentence_id")
            if s_id is not None and s_id not in seen_sentences:
                seen_sentences.add(s_id)
                current_sentence = Sentence(id=s_id, state=DataState.SYNC)
                if current_paragraph is not None:
                    current_paragraph.sentences.append(current_sentence)

            t_id = rec.get("token_id")
            if t_id is not None and current_sentence is not None:
                _type = Type(rec["token_type"]) if rec.get("token_type") else Type._
                _pos = POS(rec["token_pos"]) if rec.get("token_pos") else POS._
                token = Token(
                    id=t_id,
                    text=rec.get("token_text", ""),
                    type=_type,
                    trailing_ws=rec.get("token_trailing_ws", ""),
                    pos=_pos,
                    lemma=rec.get("token_lemma", ""),
                    is_digit=bool(rec.get("token_is_digit", False)),
                    like_num=bool(rec.get("token_like_num", False)),
                    is_alpha=bool(rec.get("token_is_alpha", False)),
                    is_stop=bool(rec.get("token_is_stop", False)),
                    state=DataState.SYNC,
                )
                current_sentence.tokens.append(token)

        logger.debug("Loaded Chapter: %d paragraphs", len(chapter.paragraphs))
        return chapter
