// A document title is unique per account, mirroring chapter_title_key_per_document.
// Two accounts may each hold a document called "Opening"; each sees only their own,
// and neither account's manuscript tree can collide with the other's on disk.
//
// A document with no `owner` property predates ownership, belongs to nobody, and is
// reachable only through `dockb users assign`. Neo4j excludes nodes missing any
// property of a composite constraint from that constraint's index, so such documents
// are neither constrained nor able to block this migration. See
// neo4j/repair_empty_document_owners.cypher, which must be run first on a legacy
// database to normalize an empty owner to an absent one.
DROP CONSTRAINT document_title_key_unique IF EXISTS;
CREATE CONSTRAINT document_title_key_per_owner IF NOT EXISTS
    FOR (d:Document) REQUIRE (d.owner, d.title_key) IS UNIQUE;