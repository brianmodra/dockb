"""Repository for persisting Paragraph models to Neo4j."""

import logging
from typing import Any

from dockb.infrastructure.neo4j.base import BaseRepository
from dockb.models.base import DataState
from dockb.models.paragraph import Paragraph
from dockb.models.sentence import Sentence
from dockb.models.token import POS, Token, Type

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Write Cypher
# ---------------------------------------------------------------------------

_NEW_CYPHER = """
MATCH (c:Chapter {id: $chapter_id})
MERGE (p:Paragraph {id: $paragraph_id})
MERGE (p)-[:PART_OF]->(c)
WITH p
UNWIND $sentences AS s
MERGE (sent:Sentence {id: s.id})
MERGE (sent)-[r:PART_OF]->(p)
SET r.index = s.index
"""

_CHANGED_CYPHER = _NEW_CYPHER + """
WITH p, COLLECT(s.id) AS keep_ids
OPTIONAL MATCH (p)<-[r:PART_OF]-(orphan:Sentence)
WHERE NOT orphan.id IN keep_ids
DETACH DELETE orphan
"""

_DELETE_CYPHER = """
MATCH (p:Paragraph {id: $paragraph_id})
DETACH DELETE p
"""

# ---------------------------------------------------------------------------
# Read Cypher
# ---------------------------------------------------------------------------

_LIST_BY_CHAPTER_CYPHER = """
MATCH (p:Paragraph)-[:PART_OF]->(c:Chapter {id: $chapter_id})
RETURN p.id AS id
ORDER BY p.id
"""

_LOAD_CYPHER = """
MATCH (p:Paragraph {id: $paragraph_id})
OPTIONAL MATCH (s:Sentence)-[rs:PART_OF]->(p)
OPTIONAL MATCH (t:Token)-[rt:PART_OF]->(s)
RETURN
  p.id AS paragraph_id,
  s.id AS sentence_id, rs.index AS sentence_index,
  t.id AS token_id, rt.index AS token_index,
  t.text AS token_text, t.type AS token_type,
  t.trailing_ws AS token_trailing_ws, t.pos AS token_pos,
  t.lemma AS token_lemma, t.is_digit AS token_is_digit,
  t.like_num AS token_like_num, t.is_alpha AS token_is_alpha,
  t.is_stop AS token_is_stop
ORDER BY sentence_index, token_index
"""


class ParagraphRepository(BaseRepository[Paragraph]):
    """Persists Paragraph models to Neo4j."""

    @property
    def _new_cypher(self) -> str:
        return _NEW_CYPHER

    @property
    def _changed_cypher(self) -> str:
        return _CHANGED_CYPHER

    @property
    def _delete_cypher(self) -> str:
        return _DELETE_CYPHER

    def _build_params(self, model: Paragraph, **parent_ids: str) -> dict[str, Any]:
        return {
            "chapter_id": parent_ids["chapter_id"],
            "paragraph_id": model.id,
            "sentences": [{"id": s.id, "index": i} for i, s in enumerate(model.sentences)],
        }

    def list_by_chapter(self, chapter_id: str) -> list[dict[str, str]]:
        """Return ``[{id}]`` summaries for paragraphs belonging to *chapter_id*."""
        records = list(self._session.run(_LIST_BY_CHAPTER_CYPHER, {"chapter_id": chapter_id}))
        return [{"id": r["id"]} for r in records]

    def load(self, paragraph_id: str) -> Paragraph | None:  # pylint: disable=too-many-locals
        """Load a Paragraph and its full child hierarchy from Neo4j.

        Returns None when no paragraph with *paragraph_id* exists.
        """
        logger.debug("Load Paragraph %s", paragraph_id)
        records = list(self._session.run(_LOAD_CYPHER, {"paragraph_id": paragraph_id}))
        if not records:
            return None

        first = records[0]
        if first.get("paragraph_id") is None:
            return None

        paragraph = Paragraph(id=first["paragraph_id"], state=DataState.SYNC)

        seen_sentences: set[str] = set()
        current_sentence: Sentence | None = None

        for rec in records:
            s_id = rec.get("sentence_id")
            if s_id is not None and s_id not in seen_sentences:
                seen_sentences.add(s_id)
                current_sentence = Sentence(id=s_id, state=DataState.SYNC)
                paragraph.sentences.append(current_sentence)

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

        logger.debug("Loaded Paragraph: %d sentences", len(paragraph.sentences))
        return paragraph
