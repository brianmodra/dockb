"""ParagraphSearchRepository — matches a criteria tree against paragraphs
entirely in the database.

The one query walks Document → Chapter → Paragraph → Sentence → Token,
reconstructs each paragraph's canonical text in-database (tokens concatenated
by the whitespace each carries, each sentence rstripped, sentences joined by a
newline — byte-for-byte what the tier-1 evaluator matches against), gathers
the paragraph's MENTIONS verdicts, and answers only the paragraphs the
compiled ``WHERE`` selects, in reading order, with the sentences' ids and
texts the payload needs. No hierarchy materialization rides back to Python.
"""

from __future__ import annotations

from typing import Any

from dockb.infrastructure.neo4j.serialized_session import SessionLike

_MATCH_CYPHER = """
MATCH (d:Document {id: $document_id, owner: $owner})
MATCH (c:Chapter)-[rc:PART_OF]->(d)
MATCH (p:Paragraph)-[rp:PART_OF]->(c)
WHERE $include_characters OR coalesce(c.category, '') <> 'Character'
OPTIONAL MATCH (s:Sentence)-[rs:PART_OF]->(p)
OPTIONAL MATCH (t:Token)-[rt:PART_OF]->(s)
WITH c, rc, p, rp, s, rs, t ORDER BY rs.index, rt.index
WITH c, rc, p, rp, s,
     rTrim(reduce(txt = "", t in collect({x: coalesce(t.text, ""), w: coalesce(t.trailing_ws, "")}) | txt + t.x + t.w)) AS stext
WITH c, rc, p, rp, collect({id: s.id, text: stext}) AS sentences
WITH c, rc, p, rp, sentences,
     reduce(txt = "", i in range(0, size(sentences) - 1) |
       CASE WHEN i = 0 THEN sentences[i].text ELSE txt + "\\n" + sentences[i].text END) AS text
OPTIONAL MATCH (p)-[m:MENTIONS]->(target:Chapter)
WITH c, rc, p, rp, text, sentences, p.mentions_checked_at AS checked,
     collect({cid: target.id, stale: coalesce(m.stale, false)}) AS rels
WITH c, rc, p, rp, text, sentences, checked,
     [r IN rels WHERE NOT r.stale | r.cid] AS valid,
     any(r IN rels WHERE r.stale) AS hasStale
WHERE %s
RETURN p.id AS id, p.quote_type AS quote_type, rp.index AS index,
       c.id AS chapter_id, c.title AS chapter_title, rc.index AS chapter_index,
       sentences
ORDER BY chapter_index, index
"""

_EXISTS_CYPHER = """
MATCH (d:Document {id: $document_id, owner: $owner})
RETURN d.id AS id
"""

_DIRECTORY_CYPHER = """
MATCH (c:Chapter)-[:PART_OF]->(d:Document {id: $document_id, owner: $owner})
WHERE c.category = 'Character'
RETURN c.id AS id, c.title AS title, c.first_name AS first_name,
       c.middle_names AS middle_names, c.surname AS surname,
       c.nicknames AS nicknames
ORDER BY c.title
"""


class ParagraphSearchRepository:
    """Reads the paragraphs a compiled criteria expression selects, owner-scoped."""

    def __init__(self, session: SessionLike) -> None:
        self._session = session

    def document_exists(self, document_id: str, owner: str) -> bool:
        """Whether *owner* owns a document with *document_id*.

        The one cheap lookup that lets the search answer an unknown or
        other-account id differently from a known one with no matches.
        """
        records = list(self._session.run(_EXISTS_CYPHER, {"document_id": document_id, "owner": owner}))
        return bool(records)

    def character_directory(self, document_id: str, owner: str) -> list[dict[str, Any]]:
        """The document's character chapters: id, title, and the name fields.

        A handful of small rows — everything a character reference needs to
        resolve (by id, title, or name) and every name form it is known by,
        without loading the manuscript.
        """
        records = list(self._session.run(_DIRECTORY_CYPHER, {"document_id": document_id, "owner": owner}))
        return [
            {
                "id": str(record["id"]),
                "title": str(record.get("title") or ""),
                "first_name": str(record.get("first_name") or ""),
                "middle_names": list(record.get("middle_names") or []),
                "surname": str(record.get("surname") or ""),
                "nicknames": list(record.get("nicknames") or []),
            }
            for record in records
        ]

    def match_paragraphs(
        self,
        document_id: str,
        owner: str,
        *,
        compiled: tuple[str, dict[str, Any]],
        include_characters: bool,
    ) -> list[dict[str, Any]]:
        """The paragraphs *compiled* selects, in reading order, as plain payload rows.

        *compiled* is the criteria tree as ``(where, params)`` — a Cypher
        expression over ``text``, ``checked``, ``valid`` and ``hasStale``, and
        the values its leaves carry (``criteria_cypher.compile_criteria``).
        Character chapters are searched only when *include_characters* is set.
        Every match carries its chapter, its position there, its quote type,
        and its sentences' ids and canonical texts.
        """
        where, where_params = compiled
        query_params: dict[str, Any] = {"document_id": document_id, "owner": owner, "include_characters": include_characters}
        query_params.update(where_params)
        records = list(self._session.run(_MATCH_CYPHER % where, query_params))
        return [
            {
                "id": str(record["id"]),
                "quote_type": str(record.get("quote_type") or ""),
                "index": int(record.get("index") or 0),
                "chapter_id": str(record["chapter_id"]),
                "chapter_title": str(record.get("chapter_title") or ""),
                "chapter_index": int(record.get("chapter_index") or 0),
                "sentences": [
                    {"id": str(sentence["id"]), "text": str(sentence.get("text") or "")} for sentence in (record.get("sentences") or [])
                ],
            }
            for record in records
        ]
