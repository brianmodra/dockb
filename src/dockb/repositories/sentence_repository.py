"""Repository for persisting Sentence models to Neo4j."""

import logging
from typing import Any

from dockb.infrastructure.neo4j.base import BaseRepository
from dockb.models.base import DataState
from dockb.models.sentence import Sentence
from dockb.models.token import POS, Token, Type
from dockb.repositories.ownership import owned_node_exists

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Write Cypher
# ---------------------------------------------------------------------------

_NEW_CYPHER = """
MATCH (p:Paragraph {id: $paragraph_id})-[:PART_OF]->(:Chapter)-[:PART_OF]->(:Document {owner: $owner})
MERGE (s:Sentence {id: $sentence_id})
MERGE (s)-[:PART_OF]->(p)
WITH s
UNWIND $tokens AS t
MERGE (tok:Token {id: t.id})
ON CREATE SET
  tok.text = t.text,
  tok.type = t.type,
  tok.trailing_ws = t.trailing_ws,
  tok.pos = t.pos,
  tok.lemma = t.lemma,
  tok.is_digit = t.is_digit,
  tok.like_num = t.like_num,
  tok.is_alpha = t.is_alpha,
  tok.is_stop = t.is_stop
ON MATCH SET
  tok.text = t.text,
  tok.type = t.type,
  tok.trailing_ws = t.trailing_ws,
  tok.pos = t.pos,
  tok.lemma = t.lemma,
  tok.is_digit = t.is_digit,
  tok.like_num = t.like_num,
  tok.is_alpha = t.is_alpha,
  tok.is_stop = t.is_stop
MERGE (tok)-[r:PART_OF]->(s)
SET r.index = t.index
"""

_CHANGED_CYPHER = _NEW_CYPHER + """
WITH s, COLLECT(t.id) AS keep_ids
OPTIONAL MATCH (s)<-[r:PART_OF]-(orphan:Token)
WHERE NOT orphan.id IN keep_ids
DETACH DELETE orphan
"""

_DELETE_CYPHER = """
MATCH (s:Sentence {id: $sentence_id})-[:PART_OF]->(:Paragraph)-[:PART_OF]->(:Chapter)-[:PART_OF]->(:Document {owner: $owner})
DETACH DELETE s
"""

# ---------------------------------------------------------------------------
# Read Cypher
# ---------------------------------------------------------------------------

_LIST_BY_PARAGRAPH_CYPHER = """
MATCH (p:Paragraph {id: $paragraph_id})-[:PART_OF]->(:Chapter)-[:PART_OF]->(:Document {owner: $owner})
MATCH (s:Sentence)-[:PART_OF]->(p)
RETURN s.id AS id
ORDER BY s.id
"""

_LOAD_CYPHER = """
MATCH (s:Sentence {id: $sentence_id})-[:PART_OF]->(:Paragraph)-[:PART_OF]->(:Chapter)-[:PART_OF]->(:Document {owner: $owner})
OPTIONAL MATCH (t:Token)-[rt:PART_OF]->(s)
RETURN
  s.id AS sentence_id,
  t.id AS token_id, rt.index AS token_index,
  t.text AS token_text, t.type AS token_type,
  t.trailing_ws AS token_trailing_ws, t.pos AS token_pos,
  t.lemma AS token_lemma, t.is_digit AS token_is_digit,
  t.like_num AS token_like_num, t.is_alpha AS token_is_alpha,
  t.is_stop AS token_is_stop
ORDER BY token_index
"""


class SentenceRepository(BaseRepository[Sentence]):
    """Persists Sentence models to Neo4j."""

    @property
    def _new_cypher(self) -> str:
        return _NEW_CYPHER

    @property
    def _changed_cypher(self) -> str:
        return _CHANGED_CYPHER

    @property
    def _delete_cypher(self) -> str:
        return _DELETE_CYPHER

    def _build_params(self, model: Sentence, **parent_ids: str) -> dict[str, Any]:
        return {
            "paragraph_id": parent_ids["paragraph_id"],
            "owner": parent_ids["owner"],
            "sentence_id": model.id,
            "tokens": [self._token_to_dict(token, index) for index, token in enumerate(model.tokens)],
        }

    def _token_to_dict(self, token: Token, index: int) -> dict[str, Any]:
        """Serialize a Token to a dict for Cypher parameters."""
        return {
            "id": token.id,
            "text": token.text,
            "type": token.type.value,
            "trailing_ws": token.trailing_ws,
            "pos": token.pos.value,
            "lemma": token.lemma,
            "is_digit": token.is_digit,
            "like_num": token.like_num,
            "is_alpha": token.is_alpha,
            "is_stop": token.is_stop,
            "index": index,
        }

    def owns_paragraph(self, paragraph_id: str, owner: str) -> bool:
        """Return whether *paragraph_id* — the parent this repository writes through — is *owner*'s.

        Asked before a create, because the write's ``MATCH`` on the paragraph that matches
        nothing writes nothing and reports no error: without this the route would answer
        200 for a sentence that does not exist.
        """
        return owned_node_exists(self._session, "Paragraph", paragraph_id, owner)

    def list_by_paragraph(self, paragraph_id: str, owner: str) -> list[dict[str, str]]:
        """Return ``[{id}]`` summaries for sentences belonging to *paragraph_id*.

        A paragraph *owner* does not own yields the same empty list as one with no
        sentences, so its existence is not confirmable from here.
        """
        records = list(self._session.run(_LIST_BY_PARAGRAPH_CYPHER, {"paragraph_id": paragraph_id, "owner": owner}))
        return [{"id": r["id"]} for r in records]

    def load(self, sentence_id: str, owner: str) -> Sentence | None:
        """Load a Sentence and its Tokens from Neo4j.

        Returns None when no sentence with *sentence_id* hangs under a document *owner*
        owns — the same answer as when no such sentence exists at all, so a sentence id
        belonging to another account is not confirmable.
        """
        logger.debug("Load Sentence %s", sentence_id)
        records = list(self._session.run(_LOAD_CYPHER, {"sentence_id": sentence_id, "owner": owner}))
        if not records:
            return None

        first = records[0]
        if first.get("sentence_id") is None:
            return None

        sentence = Sentence(id=first["sentence_id"], state=DataState.SYNC)

        for rec in records:
            t_id = rec.get("token_id")
            if t_id is not None:
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
                sentence.tokens.append(token)

        logger.debug("Loaded Sentence: %d tokens", len(sentence.tokens))
        return sentence
