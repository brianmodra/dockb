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

# ---------------------------------------------------------------------------
# Write Cypher
# ---------------------------------------------------------------------------

_NEW_CYPHER = """
MERGE (d:Document {id: $document_id})
SET d.title = $title, d.author = $author, d.owner = $owner, d.title_key = toLower($title)
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
MATCH (d:Document {id: $document_id, owner: $owner})
OPTIONAL MATCH (c:Chapter)-[:PART_OF]->(d)
OPTIONAL MATCH (p:Paragraph)-[:PART_OF]->(c)
OPTIONAL MATCH (s:Sentence)-[:PART_OF]->(p)
OPTIONAL MATCH (t:Token)-[:PART_OF]->(s)
DETACH DELETE t, s, p, c, d
"""

_LOAD_CYPHER = """
MATCH (d:Document {id: $document_id, owner: $owner})
OPTIONAL MATCH (c:Chapter)-[rc:PART_OF]->(d)
OPTIONAL MATCH (p:Paragraph)-[rp:PART_OF]->(c)
OPTIONAL MATCH (s:Sentence)-[rs:PART_OF]->(p)
OPTIONAL MATCH (t:Token)-[rt:PART_OF]->(s)
RETURN
  d.id AS document_id, d.title AS document_title, d.author AS document_author,
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

_LIST_ALL_CYPHER = """
MATCH (d:Document {owner: $owner})
RETURN d.id AS id, d.title AS title, d.author AS author
ORDER BY d.id
"""

_LOAD_SHELL_CYPHER = """
MATCH (d:Document {id: $document_id, owner: $owner})
OPTIONAL MATCH (c:Chapter)-[r:PART_OF]->(d)
WITH d, c, r ORDER BY r.index
RETURN
  d.id AS document_id, d.title AS document_title, d.author AS document_author,
  c.id AS chapter_id
"""

_FIND_SUMMARY_CYPHER = """
MATCH (d:Document {id: $document_id})
RETURN d.id AS id, d.title AS title, d.owner AS owner
"""

# A document is unowned by the *absence* of the property. `neo4j/repair_empty_document_owners.cypher`
# exists to normalize the empty-string spelling of the same fact, and the second clause
# here matches it too: a document written by an older build with a default owner of ""
# belongs to nobody as surely as one missing the property, and listing it here is what
# lets an operator give it an account instead of leaving it unreachable forever.
_LIST_UNOWNED_CYPHER = """
MATCH (d:Document)
WHERE d.owner IS NULL OR d.owner = ''
RETURN d.id AS id, d.title AS title
ORDER BY d.id
"""

_ASSIGN_OWNER_CYPHER = """
MATCH (d:Document {id: $document_id})
SET d.owner = $owner
RETURN count(d) AS assigned
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
            "title": model.title,
            "author": model.author,
            "owner": model.owner,
            "chapters": [{"id": ch.id, "index": i} for i, ch in enumerate(model.chapters)],
        }

    def list_all(self, owner: str) -> list[dict[str, str]]:
        """Return a ``{id, title, author}`` dict for every Document owned by *owner*.

        *owner* is an account id. A document with no owner — one created before
        ownership existed, or one imported without a stamp — is owned by nobody and
        so is returned to nobody; the admin CLI is what gives it an owner.
        """
        records = list(self._session.run(_LIST_ALL_CYPHER, {"owner": owner}))
        return [{"id": r["id"], "title": r["title"], "author": r["author"]} for r in records]

    def find_summary(self, document_id: str) -> dict[str, str | None] | None:
        """Return ``{id, title, owner}`` for *document_id*, or None when it does not exist.

        The one read here that answers for a document the caller does not own, so it
        exists for the CLI and admin paths that must resolve a document before they can
        scope themselves to an account — ``dockb users assign`` reads a document's title
        (to find its markdown tree) and its current owner (to know which tree to move)
        before it can ask a scoped question. Nothing serving a request may use it: a
        request already knows who it is acting for, and an unscoped read is exactly the
        existence oracle every other method here refuses to be.

        ``owner`` is None for a document with no owner property, which is how a
        pre-ownership document reads: owned by nobody, not by an account called "".
        """
        records = list(self._session.run(_FIND_SUMMARY_CYPHER, {"document_id": document_id}))
        if not records:
            return None
        record = records[0]
        owner = record.get("owner")
        return {
            "id": str(record["id"]),
            "title": str(record["title"] or ""),
            "owner": str(owner) if owner else None,
        }

    def list_unowned(self) -> list[dict[str, str]]:
        """Return ``{id, title}`` for every Document that belongs to no account.

        These are the documents ``dockb users assign`` exists for: created before
        accounts owned manuscripts, or imported before an import stamped an owner. No
        account can list, open or delete one, so nothing but this command reaches them.
        """
        records = list(self._session.run(_LIST_UNOWNED_CYPHER, {}))
        return [{"id": r["id"], "title": r["title"] or ""} for r in records]

    def assign_owner(self, document_id: str, owner: str) -> bool:
        """Give *document_id* to *owner*, whoever held it before, and report whether it matched.

        Deliberately unscoped: moving ownership *is* the operation, so scoping the write
        to the previous owner would make a transfer impossible and scoping it to the new
        one would only work for documents nobody owns. Returns False when no document
        carries *document_id*, so a caller can tell a stamp from a document that was
        deleted underneath it.

        Ownership transfer is an administrative act with no counterpart in the editor,
        which is what keeps this write out of every request path.
        """
        records = list(self._session.run(_ASSIGN_OWNER_CYPHER, {"document_id": document_id, "owner": owner}))
        if not records:
            return False
        return int(records[0].get("assigned") or 0) > 0

    def load_shell(self, id: str, owner: str) -> Document | None:  # pylint: disable=redefined-builtin
        """Load a Document's attrs and chapter ids from Neo4j — no paragraphs/sentences/tokens.

        The returned ``Document`` carries id-only ``Chapter`` stubs in
        relationship index order. Callers that only need the document's
        title (or the chapter id set) should prefer this over ``load``,
        which materializes the entire hierarchy. Returns None when *owner*
        owns no document with *id* — which is deliberately the same answer as when no
        such document exists, so an id belonging to someone else is not confirmable.
        """
        records = list(self._session.run(_LOAD_SHELL_CYPHER, {"document_id": id, "owner": owner}))
        if not records or records[0].get("document_id") is None:
            logger.debug("Document not found")
            return None

        first = records[0]
        document = Document(
            id=first["document_id"],
            title=str(first.get("document_title") or ""),
            author=str(first.get("document_author") or ""),
            owner=owner,
            state=DataState.SYNC,
        )
        seen: set[str] = set()
        for rec in records:
            ch_id = rec.get("chapter_id")
            if ch_id is not None and ch_id not in seen:
                seen.add(ch_id)
                document.chapters.append(Chapter(id=ch_id, state=DataState.SYNC))
        return document

    def load(self, id: str, owner: str) -> Document | None:  # pylint: disable=redefined-builtin,too-many-locals
        """Load a Document and its full hierarchy from Neo4j.

        Returns None when *owner* owns no document with *id*, for the same
        reason ``load_shell`` does: an unowned id and an absent one are the same answer.
        """
        logger.debug("Load Document")
        records = list(self._session.run(_LOAD_CYPHER, {"document_id": id, "owner": owner}))
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

        document = Document(
            id=first["document_id"],
            title=str(first.get("document_title") or ""),
            author=str(first.get("document_author") or ""),
            owner=owner,
            state=DataState.SYNC,
        )

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
