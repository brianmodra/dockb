"""Repository for persisting Document models to Neo4j."""

import logging
from typing import Any

from dockb.infrastructure.neo4j.base import BaseRepository
from dockb.models.document import Document

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
