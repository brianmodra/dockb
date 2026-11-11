# Document glossary (the proofreading dictionary)

## Executive Summary

This note describes the per-document list of accepted words that the spelling checker stops flagging — the invented names, dialect, and terms of art a writer has decided are correct. Each word a writer accepts is remembered for that document, so the next save does not underline it again; the writer can also open a dictionary view to add a word by hand or remove one they accepted by mistake. The list is editor state, not manuscript content, so it lives in the account store rather than the knowledge graph.

When a paragraph is checked, the effective dictionary is the stored words plus the document's own character names (a character called "Karakas" is never a spelling error). The accepted words are applied by filtering spelling findings after LanguageTool runs — they never reach LanguageTool's own shared dictionary, so the engine stays stateless and the list survives a restart.

## Storage

The glossary lives in the account SQLite store, in the `document_glossary` table keyed by
`(username, document_id, word)`. One account's words can never leak into another's document, and the
words travel with the account, not the manuscript: reassigning a document to another account does
not copy its glossary, because the dictionary is the editor's preference rather than part of the
book.

`GlossaryService` (`glossary_service.py`) is the only reader and writer. Every operation first
confirms the caller's account owns the document (`load_shell`), then delegates to
`AccountStore.get_glossary` / `set_glossary`. Words are stored trimmed and case-insensitively
deduplicated (`normalize_words`); the character names are merged only when a check runs
(`effective_words`), never persisted, so renaming a character leaves no stale word behind.

## The API

The routes are under `/api/documents/{document_id}/glossary`, wired in `controllers/glossary.py`:

| Method | Path | Effect |
|---|---|---|
| `GET` | `/api/documents/{document_id}/glossary` | Return the document's stored words. |
| `PUT` | `/api/documents/{document_id}/glossary` | Replace the whole list (`{"words": [...]}`). |
| `POST` | `/api/documents/{document_id}/glossary` | Add one word (`{"word": "..."}`), idempotent. |
| `DELETE` | `/api/documents/{document_id}/glossary/{word}` | Remove one word (case-insensitive), a no-op when absent. |

The single-word `POST` and `DELETE` are the editing surface: a client adds or removes one word at a
time instead of reading the list, mutating it, and putting it back, which two editor windows could
otherwise race over. All four return the document's words and `404` when the document is not owned
by the caller, and `503` when the glossary service is unwired. An added word is trimmed and folded
into the set case-insensitively, so "Karakas" and "karakas" are one entry.

## The dictionary view

The editor's review area carries a **Dictionary** button that opens a small modal: a text box with
an **Add** button, and beneath it the document's current words, each with an **×** to remove it.
Adding a word calls `POST`, removing one calls `DELETE`; the modal reflects the returned list, so it
stays in step with the store. A glossary failure is reported to the message log and the modal stays
open for another try, matching how the squiggle's **Add to dictionary** already reports its own
failures.

The squiggle's **Add to dictionary** (right-click a spelling underline) is the same operation as
typing the word into the modal: both add one word and re-check the paragraph. The dictionary view is
the place to see and edit the whole list; the squiggle is the shortcut for the word under the cursor.
