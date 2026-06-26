"""Repository for persisting Document models to Neo4j."""

import logging
from typing import Any

from dockb.infrastructure.neo4j.base import BaseRepository
from dockb.models.base import DataState
from dockb.models.chapter import Chapter
from dockb.models.document import Document
from dockb.models.paragraph import Paragraph
from dockb.models.sentence import Sentence
from dockb.models.token import POS, Token, Type

logger = logging.getLogger(__name__)

_NEW_CYPHER = """
MERGE (d:Document {id: $document_id})
WITH d
UNWIND $chapters AS ch
MERGE (chapter:Chapter {id: ch.id})
MERGE (chapter)-[r:PART_OF]->(d)
SET r.index = ch.index
"""

_CHANGED_CYPHER = _NEW_CYPHER + """
WITH d, COLLECT(ch.id) AS keep_ids
OPTIONAL MATCH (d)<-[r:PART_OF]-(orphan:Chapter)
WHERE NOT orphan.id IN keep_ids
DETACH DELETE orphan
"""

_DELETE_CYPHER = """
MATCH (d:Document {id: $document_id})
DETACH DELETE d
"""

_LOAD_CYPHER = """
MATCH (d:Document {id: $document_id})
OPTIONAL MATCH (c:Chapter)-[rc:PART_OF]->(d)
OPTIONAL MATCH (p:Paragraph)-[rp:PART_OF]->(c)
OPTIONAL MATCH (s:Sentence)-[rs:PART_OF]->(p)
OPTIONAL MATCH (t:Token)-[rt:PART_OF]->(s)
RETURN
  d.id AS document_id,
  c.id AS chapter_id, rc.index AS chapter_index,
  p.id AS paragraph_id, rp.index AS paragraph_index,
  s.id AS sentence_id, rs.index AS sentence_index,
  t.id AS token_id, rt.index AS token_index,
  t.text AS token_text, t.type AS token_type,
  t.trailing_ws AS token_trailing_ws, t.pos AS token_pos,
  t.lemma AS token_lemma, t.is_digit AS token_is_digit,
  t.like_num AS token_like_num, t.is_alpha AS token_is_alpha,
  t.is_stop AS token_is_stop
ORDER BY chapter_index, paragraph_index, sentence_index, token_index
"""


class DocumentRepository(BaseRepository[Document]):  # pylint: disable=too-few-public-methods
    """Persists Document models to Neo4j."""

    @property
    def _new_cypher(self) -> str:
        return _NEW_CYPHER

    @property
    def _changed_cypher(self) -> str:
        return _CHANGED_CYPHER

    @property
    def _delete_cypher(self) -> str:
        return _DELETE_CYPHER

    def _build_params(self, model: Document, **parent_ids: str) -> dict[str, Any]:
        return {
            "document_id": model.id,
            "chapters": [{"id": ch.id, "index": i} for i, ch in enumerate(model.chapters)],
        }

    def load(self, id: str) -> Document | None:  # pylint: disable=redefined-builtin,too-many-locals
        """Load a Document and its full hierarchy from Neo4j.

        Returns None when no document with *id* exists.
        """
        logger.debug("Load Document")
        records = list(self._session.run(_LOAD_CYPHER, {"document_id": id}))
        if not records:
            logger.debug("Document not found")
            return None

        first = records[0]
        if first.get("document_id") is None:
            logger.debug("Document not found")
            return None

        # Count distinct entities from the flat result set
        ch_ids = {r["chapter_id"] for r in records if r.get("chapter_id")}
        p_ids = {r["paragraph_id"] for r in records if r.get("paragraph_id")}
        s_ids = {r["sentence_id"] for r in records if r.get("sentence_id")}
        t_ids = {r["token_id"] for r in records if r.get("token_id")}
        logger.debug(
            "Loaded Document: %d chapters, %d paragraphs, %d sentences, %d tokens",
            len(ch_ids),
            len(p_ids),
            len(s_ids),
            len(t_ids),
        )

        document = Document(id=first["document_id"], state=DataState.SYNC)

        seen_chapters: set[str] = set()
        seen_paragraphs: set[str] = set()
        seen_sentences: set[str] = set()
        current_chapter: Chapter | None = None
        current_paragraph: Paragraph | None = None
        current_sentence: Sentence | None = None

        for rec in records:
            ch_id = rec.get("chapter_id")
            if ch_id is not None and ch_id not in seen_chapters:
                seen_chapters.add(ch_id)
                current_chapter = Chapter(id=ch_id, state=DataState.SYNC)
                document.chapters.append(current_chapter)

            p_id = rec.get("paragraph_id")
            if p_id is not None and p_id not in seen_paragraphs:
                seen_paragraphs.add(p_id)
                current_paragraph = Paragraph(id=p_id, state=DataState.SYNC)
                if current_chapter is not None:
                    current_chapter.paragraphs.append(current_paragraph)

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

        return document
