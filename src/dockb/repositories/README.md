# Repository classes

## Executive Summary

This note is the rulebook for the classes that read and write Neo4j: what gets read (usually one chapter, down to its tokens), what gets written (a sentence and its tokens at a time), and how deletion, ordering, and data states behave.

Read it before adding a repository method. The one performance rule that matters most: chapter-level paths read a document shell — title and chapter ids — never the whole book.

The repository is Neo4j, and it will store the models
(see @src/dockb/models/README/md).

# Reading the databse

Mostly, Dockb will need to get a chapter at a time from the database.
When it reads the Chapter object, it will therefore know about a list of Paragraphs.
So it will get the Paragraphs. From the Paragraphs, it will know about a list of Sentences,
and each Sentence will have a list of Tokens.

Chapter-level paths that only need the document's title or chapter ids use
`DocumentRepository.load_shell` (attrs + chapter id stubs, no paragraph
hierarchy). The full `load` is for paths that render whole documents, such as
materializing a document's store tree.

Every document read and write names the account that owns it: `load`, `load_shell`,
`delete` and `list_all` all take the account id, and an id belonging to another
account reads as absent rather than as an error, so a caller cannot confirm that a
document it may not see exists.

Three methods here are unscoped, and all three exist for `dockb users assign` and
nothing else:

- `find_summary(document_id)` returns `{id, title, owner}`, or None. The command needs
  a document's title to find its markdown tree and its current owner to know which tree
  to move, before it can ask a scoped question. `owner` is None when the property is
  absent, which is how a pre-ownership document reads.
- `list_unowned()` returns `{id, title}` for every document that belongs to no account,
  matching `d.owner IS NULL OR d.owner = ''`. The empty-string clause is for documents
  written by a build that defaulted the property to `""`;
  `neo4j/repair_empty_document_owners.cypher` normalizes that spelling, and listing it
  here is what lets an operator give those documents an account too.
- `assign_owner(document_id, owner)` stamps a new owner, whoever held it before, and
  returns whether a document matched. Scoping the write to the previous owner would make
  a transfer impossible; scoping it to the new one would only work for documents nobody
  owns. A False return means the document was deleted underneath the caller.

None of the three is for serving a request: a request already knows who it is acting
for, and an unscoped read is exactly the existence oracle every other method here
refuses to be. `tests/dockb/test_app_factory.py` asserts no route carries a document's
owner, so this surface stays command-line only.

## Child repositories scope through the document, not through the parent

`ChapterRepository`, `ParagraphRepository` and `SentenceRepository` take the same
account id as a required argument, and a chapter, paragraph or sentence id on its own
identifies nothing. Ownership lives only on `Document`, so every one of their queries
starts from `(:Document {owner: $owner})` and reaches the child through
`PART_OF`: a chapter from its document, a paragraph from its document (not from the
chapter it was handed), a sentence from its document. `owned_node_exists` answers the
same question for a single child id — the owner-scoped equivalent of `EXISTS` — and is
what decides whether a child id belongs to the account asking, before a write that has
no other reason to touch the document.

The consequence is that a valid child id belonging to another account is reported the
same way a child id that never existed is reported: empty from a list, `None` from a
load. The `owns_chapter` / `owns_paragraph` guards carry the account id for the same
reason — a caller that can reach a parent by id alone can reach another account's work.

`ChapterRepository.reorder` takes the account id as a required argument for the same
reason as every other method here. Nothing in this layer defaults it, because a
repository that defaulted to `""` would silently scope to nothing rather than fail.

# Writing to the database

This will mostly be a Sentence (and all its Tokens) at a time. Each model object has a unique ID,
so unless, a new sentence has been addad, or a new Token added, most of these will be updates, with a
few new objects created.

Model objects which were unchanged in memory, won't be updated in the database. The models keep track
of their state, so it will be obvious when a model object needs to be created, updated, or deleted.

# Deleting from the database

During the course of editing, some model objects will be deleted, and their corresponding object in
thedatabase will also need to be deleted by its uniqueue ID.

# Parent and Child relationship

In the model, in memory, the relationship between a child model object and it parent is maintained
in both directions: the parent has a list of children, and each child has a parent.

In the database, this relationship must be maintained. Given a certain Token object in the database,
it must be simple to traverse to its parent Sentence, find theother Tokens in the sentence,
or find other sentences in the same paragraph, etc.

The order of children in the database must match their order in memory.

# Managing state and dirty flag

The models have state. They also have a dirtty flag. The dirty flag is only used for automated
semantics, not for maintianing their state relative to the database. However, if a model's
dirty flag is set, it is not ready yet for synchronising with the database.

How do we manage that? It would be disasterous to request the models to be saved, and for it to error
out half way through. Therefore, some automation (outside of the repository classes) will need to manage
that problem. Inside the repository classes, if a model is encountered that has its dirty flag set, it must
throw an exception so that the caller can deal with the issue.

## State

The state of a model (see class DataState(Enum) in @src/dockb/models/base.py) can be
- SYNC,
- NEW,
- CHANGED,
- DELETED, or
- _ (Nothing, initial state)

If the state is _ (nothing, initial state), that object should be silently skipped rather than saved.
If the state is DELETED, then that object should be deleted from the database.
If the state is CHANGED, then that object should be changed in the database to match how it appears in memory.
If the state is NE, then the object should be created in the database.
If the state is SYNC, then it should be silently skipped, there is no need to save it.

## text

The text properties of Sentence, Paragraph, Chapter, and Document should not be saved to the database.

# Sessions

Each repository class constructor will be passed a Session object. For mopre information about them,
see @src/dockb/infrastructure/neo4j/README.md
