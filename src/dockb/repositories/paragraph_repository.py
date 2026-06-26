"""Repository for persisting Paragraph models to Neo4j."""

from typing import Any

from dockb.infrastructure.neo4j.base import BaseRepository
from dockb.models.paragraph import Paragraph

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


class ParagraphRepository(BaseRepository[Paragraph]):  # pylint: disable=too-few-public-methods
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
