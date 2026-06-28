# Design of the service to do edits on the models

## Context

JobQueue and DocCache objects are specific to a user's OAuth logged in session.
The JobQueue and DocCache, and other things, will be stored in a session context object.

### Session context

The session context (in a class SessionContext) will store the JobQueue, the DocCache,
and a queue of pending notifications for the FE (see **Async Notifications** in
controllers/README_API.md).

### Session manager

This will be in a class SessionManager, and it will persist the SessionContext, and provide methods
to put/get/remove a SessionContext.

The SessionManager maintains the SessionContext object associated with the user's account ID.
When the user's logged in session is either logged out, or times out due to inactivity,
then the SessionManager will clean up that user's SessionContext.
The SessionManager will have a method for getting a user's SessionContext object, given
user's account ID.

## ...Controller and ...Service

This document uses "...Controller" and "...Service" to mean the DocumentController and associated DocumentService,
ChapterController, ChapterService, ParagraphController, ParagraphService, SentenceController and SentenceService.

The API (FastAPI) will be responding to change requests which come from the FE.

## Models

At the point of writing this, the models (which all inherit from DockbModel), have a lot of
editing functions which I will replace with just a handful, because when I started designing
these classes I was thinking that the FE would be calling the BE with fairly fine-grained
edits. The FE could send fine grained edits, but the truth of it is that it is pointless to try
to make it "more efficient" by sending smaller edits. Every time a sentence is edited, it
will need to be re-tokenized, so the FE may as well just send the whole sentence each time.

The following methods in DockbModel will be removed (and all the associated tests)
- apply\_edit\_text
- apply\_append\_text
- apply\_insert\_text

The models will need to also gain a method:
- delete\_child(id: str) -> bool
(Which will return false if the child did not exist.)
This probably also implies that the children will need to be indexed by id in DockbCollection
rather than just a list.
A Document's children are the chapters.
A Chapter's children are the paragraphs.
A Paragraph's children are the sentences.
A Sentence's children are the tokens.

### Cascade deletion

When a model is deleted via `DELETE` API endpoint, the repository layer uses a Cypher `DETACH DELETE`
to cascade-delete all descendant nodes (e.g. deleting a paragraph deletes all its sentences and their
tokens in one Cypher query). The model layer does not need to iterate children for bulk cascade.

`model.delete_child(id)` removes a child from the parent's DockbCollection.
The child's data state becomes `DELETED` (or `_` if the child was previously `NEW`).
If the child is subsequently inserted into another parent via `insert_child`
(reparenting), its state changes to `CHANGED`. If not re-inserted, it stays
`DELETED` and will be cleaned up by the repository.
`delete_child` does not handle token-level deletion — that is the repository's job
during `DETACH DELETE`.

| Scenario | Mechanism |
|---|---|
| `DELETE /api/sentences/{id}` | Repo Cypher: `MATCH (s:Sentence {id}) DETACH DELETE s` |
| `DELETE /api/paragraphs/{id}` | Repo Cypher cascade: all sentences + tokens |
| `DELETE /api/chapters/{id}` | Repo Cypher cascade: all paragraphs + sentences + tokens |
| `DELETE /api/documents/{id}` | Repo Cypher cascade: entire hierarchy |
| Re-parent a sentence to another paragraph | `paragraph_a.delete_child(s_id)` + `paragraph_b.insert_child(s, after=...)` |

## DocumentHydrator, ChapterHydrator, ParagraphHydrator

Note there is not SentenceHydrator, because that's the SentenceTokenizer.
In the other three model types, the children are not tokens, they can be referred to as
"children" and it is obvious that a Document's children are the chapters. In the case of a
Sentence, if we refer to its "children", that would be ambiguous. It could mean phrases,
or tripples, or words, or characters - but they are actually tokens.

These hydrators will use the model's text, and split it up into the constituent parts.
They depend upon some rules:

- chapters are delimited by a double page break character
- paragraphs are delimited by double newlines.
- sentences are delimited by punctuation, but rather than specify what characters are
used in which context (e.g. the dot after "Dr" is not a sentence delimiter) the
SentenceHydrator will use spaCy's mechanism, e.g.
```
doc = nlp(text)
for i, sentence in enumerate(doc.sents, 1):
```

### Scope: import only

These hydrators run only during **initial bulk import** of raw text (e.g. pasting a manuscript).
They are not used during normal editing — the structured JSON API (controllers/README_API.md)
receives already-delimited chapters, paragraphs, and sentences in ProseMirror format.
During normal PUT/POST editing, only the SentenceTokenizer runs (via DeleteJob/ReconstructJob) to
tokenize sentence text into Token objects. The Document/Chapter/Paragraph hydrators are unused.

## How the hydration and tokenization happens

A service function will directly call model class(es) to do quick
changes. These make quick changes and leave the model
object in a "dirty" state - meaning that it as yet needs more work.

By "more work", this means tokenization or hydration, which is slow.
This sort of slow work is done in a queue (JobQueue).
The queue will have only one worker thread, and jobs added to the queue will be processed
in a FIFO manner.

When a model is edited and becomes "dirty", its dirty flag will be set to True.
Then the service function will create two jobs.
The first job added to the queue will be to delete the existing semantics associated with
the model object.
The second job will be to re-create the semantics.

This second job could potentially have a problem, because the ...Service
functions will be called in response to async calls from the front end as the user is typing away
and creating lots of edit requests in fairly quick succession.
Any jobs currently queued for the same sentence, or in progress, could be creating semantics which will be
invalidated by the latest edit.
So if they are queued, they should be cancelled, and if one is currently running, it should be stopped.

### Sentence split detection during ReconstructJob

The second job (ReconstructJob) does more than tokenization. It also detects
sentence splits. For a sentence whose dirty flag is set, spaCy is run on the
text to identify linguistic sentence boundaries. If the text contains multiple
sentences, the ReconstructJob:

1. Creates new Sentence model objects for each split
2. Updates the parent paragraph's children list to include the new sentences
3. Sets each new sentence's data state to `NEW`
4. Truncates the original sentence's text to its portion
5. Queues a `sentence_split` notification in the SessionContext

The notification is delivered to the FE via piggy-back or poll (see **Async
Notifications** in controllers/README_API.md).

## Jobs, worker tasks, and the JobQueue

See the file @src/dockb/services/semantics/README.md

## Editing Design

See the file @src/dockb/services/README_editing.md
