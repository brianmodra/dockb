"""Repository for persisting Sentence models to Neo4j."""

import logging
from collections.abc import Sequence
from typing import Any

from dockb.infrastructure.neo4j.base import BaseRepository
from dockb.infrastructure.neo4j.serialized_session import SessionLike
from dockb.models.base import DataState
from dockb.models.formatting import Family, Style, Weight
from dockb.models.sentence import Sentence, flatten_dialogue_spans, sentence_from_record
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
  tok.is_stop = t.is_stop,
  tok.style = t.style,
  tok.weight = t.weight,
  tok.family = t.family,
  tok.size = t.size
ON MATCH SET
  tok.text = t.text,
  tok.type = t.type,
  tok.trailing_ws = t.trailing_ws,
  tok.pos = t.pos,
  tok.lemma = t.lemma,
  tok.is_digit = t.is_digit,
  tok.like_num = t.like_num,
  tok.is_alpha = t.is_alpha,
  tok.is_stop = t.is_stop,
  tok.style = t.style,
  tok.weight = t.weight,
  tok.family = t.family,
  tok.size = t.size
MERGE (tok)-[r:PART_OF]->(s)
SET r.index = t.index
"""

_INVALIDATE_DIALOGUE_CYPHER = """
WITH s
OPTIONAL MATCH (s)-[spoken:SPOKEN_BY]->(:Chapter)
SET spoken.stale = true
SET s.dialogue_checked_at = null
"""

_CHANGED_CYPHER = _NEW_CYPHER + """
WITH s, COLLECT(t.id) AS keep_ids
OPTIONAL MATCH (s)<-[r:PART_OF]-(orphan:Token)
WHERE NOT orphan.id IN keep_ids
DETACH DELETE orphan
""" + _INVALIDATE_DIALOGUE_CYPHER

_DELETE_CYPHER = """
MATCH (s:Sentence {id: $sentence_id})-[:PART_OF]->(:Paragraph)-[:PART_OF]->(:Chapter)-[:PART_OF]->(:Document {owner: $owner})
DETACH DELETE s
"""

# ---------------------------------------------------------------------------
# Batched write Cypher — the same writes over `UNWIND $rows AS row`.
# ---------------------------------------------------------------------------

_NEW_ROWS_CYPHER = """
UNWIND $rows AS row
MATCH (p:Paragraph {id: row.paragraph_id})-[:PART_OF]->(:Chapter)-[:PART_OF]->(:Document {owner: row.owner})
MERGE (s:Sentence {id: row.sentence_id})
MERGE (s)-[:PART_OF]->(p)
WITH s, row
UNWIND row.tokens AS t
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
  tok.is_stop = t.is_stop,
  tok.style = t.style,
  tok.weight = t.weight,
  tok.family = t.family,
  tok.size = t.size
ON MATCH SET
  tok.text = t.text,
  tok.type = t.type,
  tok.trailing_ws = t.trailing_ws,
  tok.pos = t.pos,
  tok.lemma = t.lemma,
  tok.is_digit = t.is_digit,
  tok.like_num = t.like_num,
  tok.is_alpha = t.is_alpha,
  tok.is_stop = t.is_stop,
  tok.style = t.style,
  tok.weight = t.weight,
  tok.family = t.family,
  tok.size = t.size
MERGE (tok)-[r:PART_OF]->(s)
SET r.index = t.index
"""

_CHANGED_ROWS_CYPHER = _NEW_ROWS_CYPHER + """
WITH s, COLLECT(t.id) AS keep_ids
OPTIONAL MATCH (s)<-[r:PART_OF]-(orphan:Token)
WHERE NOT orphan.id IN keep_ids
DETACH DELETE orphan
""" + _INVALIDATE_DIALOGUE_CYPHER

_DELETE_ROWS_CYPHER = """
UNWIND $rows AS row
MATCH (s:Sentence {id: row.sentence_id})-[:PART_OF]->(:Paragraph)-[:PART_OF]->(:Chapter)-[:PART_OF]->(:Document {owner: row.owner})
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
  s.is_dialogue AS sentence_is_dialogue,
  s.dialogue_start_token AS sentence_dialogue_start_token,
  s.dialogue_end_token AS sentence_dialogue_end_token,
  s.dialogue_checked_at AS sentence_dialogue_checked_at,
  s.dialogue_spans AS sentence_dialogue_spans,
  t.id AS token_id, rt.index AS token_index,
  t.text AS token_text, t.type AS token_type,
  t.trailing_ws AS token_trailing_ws, t.pos AS token_pos,
  t.lemma AS token_lemma, t.is_digit AS token_is_digit,
  t.like_num AS token_like_num, t.is_alpha AS token_is_alpha,
  t.is_stop AS token_is_stop,
  t.style AS token_style, t.weight AS token_weight,
  t.family AS token_family, t.size AS token_size
ORDER BY token_index
"""

_STAMP_DIALOGUE_CYPHER = """
UNWIND $rows AS row
MATCH (s:Sentence {id: row.sentence_id})-[:PART_OF]->(:Paragraph)-[:PART_OF]->(:Chapter)-[:PART_OF]->(:Document {owner: row.owner})
SET s.is_dialogue = row.is_dialogue,
    s.dialogue_start_token = row.start_token,
    s.dialogue_end_token = row.end_token,
    s.dialogue_checked_at = row.checked_at,
    s.dialogue_spans = row.spans
WITH s, row
UNWIND row.tokens AS token
MATCH (t:Token {id: token.id})-[rt:PART_OF]->(s)
SET t.text = token.text, t.trailing_ws = token.trailing_ws
"""

_STAMP_SPOKEN_BY_CYPHER = """
UNWIND $rows AS row
MATCH (s:Sentence {id: row.sentence_id})-[:PART_OF]->(:Paragraph)-[:PART_OF]->(:Chapter)-[:PART_OF]->(:Document {owner: row.owner})
OPTIONAL MATCH (s)-[old:SPOKEN_BY]->(:Chapter)
SET old.stale = true
WITH s, row
MERGE (c:Chapter {id: row.character_id})
ON CREATE SET c.category = 'Character', c.title = 'unresolved'
WITH s, c, row
MERGE (s)-[spoken:SPOKEN_BY]->(c)
SET spoken.method = row.method,
    spoken.confidence = row.confidence,
    spoken.stale = row.stale,
    spoken.reference = row.reference
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
            "style": token.style.value,
            "weight": token.weight.value,
            "family": token.family.value,
            "size": token.size,
            "index": index,
        }

    def save_many(
        self,
        entries: list[tuple[Sentence, dict[str, str]]],
        *,
        session: SessionLike | None = None,
    ) -> None:
        """Persist many sentences — one UNWIND query per data state."""
        for model, _ in entries:
            if model.dirty:
                raise ValueError(f"{type(model).__name__} is dirty, cannot save")
        for state, cypher in (
            (DataState.NEW, _NEW_ROWS_CYPHER),
            (DataState.CHANGED, _CHANGED_ROWS_CYPHER),
            (DataState.DELETED, _DELETE_ROWS_CYPHER),
        ):
            rows = [self._build_params(model, **parent_ids) for model, parent_ids in entries if model.state is state]
            self._run_batched(cypher, rows, session=session)

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

        sentence = sentence_from_record(first)

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
                    style=Style(rec["token_style"]) if rec.get("token_style") else Style._,
                    weight=Weight(rec["token_weight"]) if rec.get("token_weight") else Weight._,
                    family=Family(rec["token_family"]) if rec.get("token_family") else Family._,
                    size=rec.get("token_size") or "",
                    state=DataState.SYNC,
                )
                sentence.tokens.append(token)

        logger.debug("Loaded Sentence: %d tokens", len(sentence.tokens))
        return sentence

    def stamp_dialogue(
        self,
        stamps: Sequence[dict[str, Any]],
        *,
        owner: str,
        session: SessionLike | None = None,
    ) -> None:
        """Stamp dialogue verdicts, token ranges, and quote fixes onto sentences."""
        rows = [{**stamp, "owner": owner, "spans": flatten_dialogue_spans(stamp.get("spans", []))} for stamp in stamps]
        self._run_batched(_STAMP_DIALOGUE_CYPHER, rows, session=session)

    def stamp_spoken_by(
        self,
        rows: Sequence[dict[str, Any]],
        *,
        owner: str,
        session: SessionLike | None = None,
    ) -> None:
        """Write SPOKEN_BY edges for dialogue sentences."""
        owned_rows = [{**row, "owner": owner} for row in rows]
        self._run_batched(_STAMP_SPOKEN_BY_CYPHER, owned_rows, session=session)
