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

_NEW_CYPHER = """
MATCH (d:Document {id: $document_id})
MERGE (c:Chapter {id: $chapter_id})
SET c.title = $title
MERGE (c)-[:PART_OF]->(d)
WITH c
UNWIND $paragraphs AS p
MERGE (para:Paragraph {id: p.id})
MERGE (para)-[r:PART_OF]->(c)
SET r.index = p.index
"""

_CHANGED_CYPHER = _NEW_CYPHER + """
WITH c, COLLECT(p.id) AS keep_ids
OPTIONAL MATCH (c)<-[r:PART_OF]-(orphan:Paragraph)
WHERE NOT orphan.id IN keep_ids
DETACH DELETE orphan
"""

_DELETE_CYPHER = """
MATCH (c:Chapter {id: $chapter_id})
DETACH DELETE c
"""

# ---------------------------------------------------------------------------
# Read Cypher
# ---------------------------------------------------------------------------

_LIST_BY_DOCUMENT_CYPHER = """
MATCH (c:Chapter)-[:PART_OF]->(d:Document {id: $document_id})
RETURN c.id AS id, c.title AS title
ORDER BY c.id
"""

_LOAD_CYPHER = """
MATCH (c:Chapter {id: $chapter_id})
OPTIONAL MATCH (p:Paragraph)-[rp:PART_OF]->(c)
OPTIONAL MATCH (s:Sentence)-[rs:PART_OF]->(p)
OPTIONAL MATCH (t:Token)-[rt:PART_OF]->(s)
RETURN
  c.id AS chapter_id, c.title AS chapter_title,
  p.id AS paragraph_id, rp.index AS paragraph_index,
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
            "chapter_id": model.id,
            "title": model.title,
            "paragraphs": [{"id": p.id, "index": i} for i, p in enumerate(model.paragraphs)],
        }

    def list_by_document(self, document_id: str) -> list[dict[str, str]]:
        """Return ``[{id, title}]`` summaries for chapters belonging to *document_id*."""
        records = list(self._session.run(_LIST_BY_DOCUMENT_CYPHER, {"document_id": document_id}))
        return [{"id": r["id"], "title": r.get("title") or ""} for r in records]

    def load(self, chapter_id: str) -> Chapter | None:  # pylint: disable=too-many-locals
        """Load a Chapter and its full child hierarchy from Neo4j.

        Returns None when no chapter with *chapter_id* exists.
        """
        logger.debug("Load Chapter %s", chapter_id)
        records = list(self._session.run(_LOAD_CYPHER, {"chapter_id": chapter_id}))
        if not records:
            return None

        first = records[0]
        if first.get("chapter_id") is None:
            return None

        chapter = Chapter(
            id=first["chapter_id"],
            title=first.get("chapter_title") or "",
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
                current_paragraph = Paragraph(id=p_id, state=DataState.SYNC)
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
