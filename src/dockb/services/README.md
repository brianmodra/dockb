# Design of the service to do edits on the models

## Executive Summary

This note explains how DockB edits a document after the text is already saved: session queues, re-tokenization, sentence splits, and deletion. It also covers the chapter-file front matter that the graph mirrors by hand — who a character is, whose point of view a chapter is written from — and the whole-document chapter operations that live beside them: renumbering a document's chapters in their current reading order (from 1, or 0) after moves have shuffled the title numbers, which is planned in full before anything is written and lands as one graph query plus one git commit. It is for someone changing those editing services, not the files on disk.

Interactive proofreading also lives here: `ProofreadingService` checks one paragraph with LanguageTool, starting from the resolved `DOCKB_PROOFREADING_LANGUAGE`, and `GlossaryService` keeps each document's accepted words, merging them with its character names at check time. Every service method names the account it acts for as a required keyword argument, and no service may default it: an account is something the caller states, so a service cannot be handed a document id and quietly guess whose work it is. Chapter-level paths keep their document loads light (title and chapter ids), so opening a chapter never pulls the whole book. Publishing a finished manuscript is not built yet; when it is, a character chapter stays out of it.

### Publishing

Publishing a manuscript is a later feature. There is no whole-book exporter. When it is added, a
`Character` chapter is never published. Only `category` `Chapter` is manuscript text.

### Shell loads

Chapter-level paths (open, save, create, rename, delete, and the store export) load the owning
document through `DocumentRepository.load_shell` — attrs and chapter ids only — because they read
the title, never the hierarchy. The full load is reserved for document-level paths.

### Chapter front matter: character properties and POV

`services/chapter_front_matter.py` owns the sync between a chapter file's YAML
front matter and the graph for the hand-maintained side: a `Character`
chapter's identity properties (first name, surname, middle names, nicknames,
age, location) and a manuscript chapter's `pov` — the character chapter whose
point of view it is written from. The file carries the character's **title**;
the graph stores the character chapter's **id**, so renaming a character does
not break a POV, and a deleted one warns on read and clears on the next save.
`set_pov` matches a typed name case-insensitively — one word against the first
name, then a nickname, then the surname; two words the first and surname in
that order; three or more the full joined name — and, failing that, suggests a
character whose name contains the typed text (at least three characters)
without applying it.

### Renumbering chapters

`ChapterService.renumber(document_id, owner)` renumbers every act chapter of one
document, from a requested start (1 by default, 0 on request), in the display order
(`PART_OF.index`) — the order the editor
lists, which drifts out of step with the title numbers once chapters are moved.
`Character` chapters carry no number and are untouched, but their titles count when the
new titles are checked: a case-insensitive duplicate raises `DuplicateTitleError` before
anything is written, so a renumber can never walk over a character. The new number is
rewritten in place in the title, by the same rule the import walker uses to order files
(`dockb/chapter_numbers.py`); the letter suffix goes, and a title with no number gains
one at the end. The plan is computed before anything is written; the graph titles then
change in one transaction (`ChapterRepository.retitle`) — the renumbered chapters' title
keys clear to their ids first, so renumbering through each other cannot trip the
(`document_id`, `title_key`) uniqueness constraint — and
the files move through the store's `renumber_chapters` and its single git commit. The
route is `POST /api/chapters/renumber` with the document id, answering the
`{id, old_title, new_title}` list of what changed.

### Proofreading

`ProofreadingService` (`services/proofreading.py`) answers `POST /api/check` for one paragraph
with LanguageTool spelling, grammar and style diagnostics. The engine starts lazily per language
on the first check and is stopped on `unwire`; it is reached only here, so the manuscript text
never leaves the process unless an operator points `DOCKB_LANGUAGETOOL_URL` at an external
server. Checks are cached briefly, serialized on one lock because the LanguageTool client is not
thread-safe, and never write the graph, the file, or a snapshot. Diagnostics carry
paragraph-relative offsets, the rule, category, severity, message and replacements; the route
maps an empty or oversized paragraph and an unsupported language to `422`, a disabled or
unreachable engine to `503`, and a failed check to `502`. The editor's starting language is the
resolved `DOCKB_PROOFREADING_LANGUAGE`, advertised by `GET /api/check/languages` as `default`.

The route hands the service the paragraph text, the focused sentence's offsets, and the
document's effective glossary, so accepted character names are filtered out of spelling
diagnostics instead of being added to LanguageTool's shared user dictionary. A quote diagnostic
(`EN_QUOTES`, `EN_UNPAIRED_BRACKETS`) whose partner sits in the same paragraph also carries a
`pair` naming the partner's offsets and the correction for both quotes, so the editor can offer a
single click that turns a mismatched or straight pair into matching curly quotes. The partner is
re-found by a same-paragraph scan (apostrophes are skipped), so it is best-effort and absent when
no partner exists.

### Glossary

`GlossaryService` (`services/glossary_service.py`) owns the per-document accepted-word list and
the merge used by checks. The stored words live in SQLite under the signed-in username and the
document id (`AccountStore.get_glossary`/`set_glossary`); every operation first confirms the
account owns the document through `DocumentRepository.load_shell`, so another account's document
is indistinguishable from a missing one. `set_words` trims blanks and removes case-insensitive
duplicates, and GET returns only what was stored. `add_word` and `remove_word` edit one word at a
time — the single-word editing surface that `POST`/`DELETE` expose, so two editor windows cannot
race by reading the list, mutating it, and putting it back. `effective_words` merges those stored words with
the document's character names from `ChapterRepository.list_character_names` at check time; the
names are never persisted into the glossary, so editing a character name cannot leave a stale
word behind. The routes are `GET`/`PUT`/`POST /api/documents/{document_id}/glossary` and
`DELETE /api/documents/{document_id}/glossary/{word}`.

## Character mentions

The paragraph-to-character mention pipeline (candidates, the model's judgement,
the MENTIONS cache and its four paragraph states) is designed in
[README_mentions.md](README_mentions.md).

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

**Every service method names the account it acts for, as a required keyword
argument `owner`.** There is one rule for reads, writes and deletes alike, and no
default: an account is something a caller states, not something it can drop in as
another positional argument and have a service guess. A service that could read for
"nobody" would quietly answer "not found" for everything — a failure that looks like
missing data — so the argument is required rather than optional.

The account id comes from the session at the route, and the service passes it to the
repository, which scopes the Cypher to `(:Document {owner: $owner})`. See
`../repositories/README.md` for what that means for the query itself.

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
