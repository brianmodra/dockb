// One-time data repair for databases created before the case-insensitive
// unique-title feature. Derives the identity props that the V002 constraints
// require, so they can be applied to an existing tree. Run this BEFORE
// `make migrate` on any legacy database; fresh databases are unaffected
// because V002 is never combined with write statements (Neo4j forbids mixing
// data writes with schema DDL in a single migration transaction).
MATCH (d:Document) WHERE d.title_key IS NULL
SET d.title_key = toLower(d.title);

MATCH (c:Chapter)-[:PART_OF]->(d:Document)
WHERE c.title IS NOT NULL AND (c.document_id IS NULL OR c.title_key IS NULL)
SET c.document_id = d.id, c.title_key = toLower(c.title);