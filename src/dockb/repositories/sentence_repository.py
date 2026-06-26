"""Repository for persisting Sentence models to Neo4j."""

from typing import Any

from dockb.infrastructure.neo4j.base import BaseRepository
from dockb.models.sentence import Sentence
from dockb.models.token import Token

_NEW_CYPHER = """
MATCH (p:Paragraph {id: $paragraph_id})
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
MATCH (s:Sentence {id: $sentence_id})
DETACH DELETE s
"""


class SentenceRepository(BaseRepository[Sentence]):  # pylint: disable=too-few-public-methods
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
