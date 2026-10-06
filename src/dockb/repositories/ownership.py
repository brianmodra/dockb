"""Whether a node belongs to the account that owns its document.

Every node below a document — chapter, paragraph, sentence — is reachable only through
that document, so a query about one of them is scoped by joining to
``(:Document {owner: $owner})``. Reads need nothing more: a node nobody in this account
owns simply does not match, and the caller is handed nothing.

Writes are the reason this exists. A ``MERGE`` whose ``MATCH`` finds nothing writes
nothing and reports no error, so creating a paragraph under another account's chapter
would answer 200 for a write that never happened. A service therefore asks first, and
this is the question it asks.

The label is interpolated rather than parameterized because Cypher cannot parameterize
one. Every label here is a repository's own constant, never anything a caller supplies,
so there is nothing to inject.
"""

from __future__ import annotations

from neo4j import Session

_OWNED_CYPHER = """
MATCH (n:{label} {{id: $id}})-[:PART_OF*1..3]->(d:Document {{owner: $owner}})
RETURN count(n) AS owned
"""


def owned_node_exists(session: Session, label: str, node_id: str, owner: str) -> bool:
    """Return whether *node_id* hangs under a Document owned by *owner*.

    *label* is the node's own label — ``Chapter``, ``Paragraph`` or ``Sentence`` — and
    is a constant of the calling repository. The hop count covers the deepest chain in
    use (sentence → paragraph → chapter → document) and is bounded so an unrelated
    cycle elsewhere in the graph cannot make this walk forever.
    """
    records = list(session.run(_OWNED_CYPHER.format(label=label), {"id": node_id, "owner": owner}))
    if not records:
        return False
    return int(records[0].get("owned") or 0) > 0
