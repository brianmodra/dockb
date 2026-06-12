"""Repository for persisting Chapter models to Neo4j."""

import logging
from typing import Any

from dockb.infrastructure.neo4j.base import BaseRepository
from dockb.models.chapter import Chapter

logger = logging.getLogger(__name__)

_NEW_CYPHER = """
MATCH (d:Document {id: $document_id})
MERGE (c:Chapter {id: $chapter_id})
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


class ChapterRepository(BaseRepository[Chapter]):  # pylint: disable=too-few-public-methods
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
            "paragraphs": [{"id": p.id, "index": i} for i, p in enumerate(model.paragraphs)],
        }
