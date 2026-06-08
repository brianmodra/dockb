# Repository classes

The repository is Neo4j, and it will store the models
(see @src/dockb/models/README/md).

# Reading the databse

Mostly, Dockb will need to get a chapter at a time from the database.
When it reads the Chapter object, it will therefore know about a list of Paragraphs.
So it will get the Paragraphs. From the Paragraphs, it will know about a list of Sentences,
and each Sentence will have a list of Tokens.

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
If the state is NE, then the object should be created in teh database.
If the state is SYNC, then it should be silently skipped, there is no need to save it.

