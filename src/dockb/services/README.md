# Design of the service to do edits on the models

## Context

JobQueue and DocCache objects are specific to a user's OAuth logged in session.
The JobQueue and DocCache, and other things, will be stored in a session context object.

### Session context

The session context (in a class SessionContext) will store the JobQueue and the DocCache.

### Session manager

This will be in a class SessionManager, and it will persist the SessionContext, and provide methods
to put/get/remove a SessionContext.

The SessionManager maintains the SessionContext object associated with the user's account ID.
When the user's logged in session is either logged out, or times out due to inactivity,
then the SessionManager will clean up that user's SessionContext.
The SessionManager will have a method for getting a user's SessionContext object, given
user's account ID.

## EventController and EventService

The API (FastAPI) will be responding to change events which come from the FE and originate from Lexical,
e.g. a payload (this is not a design, just an example from my thoughts at this point in time before
designing the actual API)

``` json
{
  nodeKey: "paragraph-1",
  before: {
    type: "paragraph",
    children: [{ text: "Hello" }]
  },
  after: {
    type: "paragraph",
    children: [{ text: "Hello world" }]
  }
}
```
Therefore, the EventController will be quite simple, and we will have a corresponding EventService class.
The EventService class will look at the request, and create one or more calls to model-specific
service objects.

There won't be a controller for each type of model, but there will be a controller-service pairing.
There won't even be a service-model pairing, but there may be domain service classes.

## Model-specific Service classes

There won't be any.

The EventService will mostly just call the models directly, though in some cases if it becomes obvious
we need to do extra domain-type functions before calling a model class, then the EventService
will call a domain service class, and then it will call the models.

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

This second job could potentially have a problem, because the EventService
functions will be called in response to async calls from the front end as the user is typing away
and creating lots of edit requests in fairly quick succession.
Any jobs currently queued for the same sentence, or in progress, could be creating semantics which will be
invalidated by the latest edit.
So if they are queued, they should be cancelled, and if one is currently running, it should be stopped.

## Jobs, worker tasks, and the JobQueue

See the file @src/dockb/services/semantics/README.md

## Editing Design

See the file @src/dockb/services/README_editing.md
