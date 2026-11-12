# Right panel — read-only chapters

## Executive Summary

The right panel is the editor's reference shelf: it shows other chapters of the
book, read-only, while the writer works in the main edit panel. A strip of tabs
sits across its top, one tab per chapter on the shelf. Two things put a chapter
there: the writer asks for one (a menu item, or a button in the response area),
and, automatically, the characters that the paragraph under the cursor mentions
— so the writer sees, at a glance, who is in the scene they are writing. The
auto character tabs follow the cursor; the writer-added ones stay until closed.
The panel now defaults to the same width as the chapter list instead of hiding
at the edge.

A chapter on the shelf is the writer's own markdown file, shown rendered but
not editable. The file is never re-read or re-written through the graph just to
display it: if the file already exists it is shown as-is, and only a missing
file is hydrated (written from the graph) first. Which characters a paragraph
mentions comes from the stored MENTIONS verdicts, fetched once per document, so
an unsaved paragraph shows the verdicts of its last saved state.

## 1. The panel and the tab strip

The right panel sits to the right of the edit panel, the mirror of the chapter
list on the left. It defaults to the same width as that list (about 240 px,
draggable at its seam as today) rather than the 10 px sliver it starts at now.

A tab strip runs across the top of the panel. Each tab names one chapter, with
the title truncated to at most 12 characters: a title of 12 or fewer shows
whole; a longer one shows its first 9 characters followed by `…`. Tabs are
ordered left to right — the writer-added chapters first, then the automatic
character chapters.

Below the strip the panel shows the *opened* chapter — the one whose tab is
active — rendered read-only. Clicking a tab opens it. At any time at most one
tab is open; the strip itself always lists every tab.

If the panel is not wide enough to show all the tabs at once in one row, then it will show as many rows as are required.

## 2. Writer-added chapters

A writer adds a chapter to the shelf in two ways:

- **The chapter list's right-click menu** gains a `Read-only view` item, a
  sibling of `Edit`. Choosing it adds that chapter's tab; choosing it for a
  chapter already on the shelf does nothing (idempotent).
- **A response-area button** (below) adds the chapter, scrolled to a paragraph.

Writer-added tabs carry an `×`. They stay on the shelf until the writer closes
them, independent of the cursor, and always sit to the left of the automatic
character tabs.

## 3. Automatic character tabs

While the writer edits a paragraph, the panel lists a tab for each character
chapter that paragraph's stored verdicts say it mentions. Moving the cursor to
another paragraph *replaces* this automatic set with the new paragraph's
characters. If the currently-open tab was one of these automatic character tabs
and the new paragraph does not mention that character, the panel simply shows
nothing — the tab is gone from the strip until the writer clicks one again.

The source of truth is the **mention map** (section 5): the cached paragraph →
characters verdicts, not a live re-match of the text. A paragraph that has never
been saved has no verdicts yet, so it shows no automatic tabs until a save has
run the mention pipeline.

## 4. Read-only content

The opened chapter is the writer's markdown file, rendered (span markup
stripped, markdown rendered) and not editable. Displaying it does not refresh it
from the graph:

- if the chapter's markdown file **exists**, it is read and shown **as-is** — no
  reconciliation, no re-tokenisation, no git write;
- if the file **does not exist**, it is **hydrated** first (serialised from the
  graph, written, and committed, exactly as the edit panel does when it first
  opens a chapter), then shown.

This is deliberately lighter than opening for editing, which re-reads the file
back through the graph on every open.

## 5. The mention map (data for the automatic tabs)

The automatic character tabs read a per-document **mention map**: for each
paragraph, the character chapters its *valid* (state 3) MENTIONS verdicts name.
It is served by a new endpoint, `GET /api/documents/{document_id}/mentions`,
returning `{ "mentions": { "<paragraph_id>": ["<character_id>", …] } }` — only
paragraphs with at least one valid mention.

The frontend fetches the map when it opens a document and pairs it with the
paragraph id the edit panel reports for the cursor (`proofreadingParagraph()`)
to derive the automatic tabs. Because the map is the cached verdicts, an unsaved
edit lags: the tabs reflect the paragraph's last saved mention state. The map is
read once, at open, and **not re-read after a save** — the mention pipeline
recalculates verdicts asynchronously, so a read right after a save would be
unreliable.

## 6. Opening scrolled to a paragraph (response-area function)

A new response-area function, registered beside `highlight`, opens a read-only
chapter positioned so a given paragraph is in view. Its button args are
`{ "chapter_id": "…", "paragraph_id": "…" }`. Calling it **adds** the chapter as
a writer-added tab (persisting, with its `×`) and scrolls the named paragraph
into view. This is the hook the model will later use to offer the writer
contextually relevant chapters, as `highlight` already offers sentences.

## 7. Backend work this implies

- `GET /api/documents/{document_id}/mentions` — the paragraph → character-chapter
  mention map (the state-3 verdicts `MentionsRepository` already reads).
- A read-only chapter content path on the existing
  `GET /api/chapters/{chapter_id}/document` route, selected by a query flag (e.g.
  `?readonly=1`): `read_chapter` from the store when the file exists, else
  materialise-then-read — without the `apply_chapter_file` reconciliation
  `open_document` performs.

## 8. Later

- The model may offer "show me X" buttons that call the scroll-to-paragraph
  function for contextually relevant chapters — no new plumbing, just prompts.
