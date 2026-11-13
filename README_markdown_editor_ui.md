# Markdown Editor UI Design

## Executive Summary

This is the design of DockB's writing window. It explains the menus, chapter list, editor, and
dialogs, so someone new can see what the writer sees and why each click does what it does. It
covers proofreading in both the WYSIWYG and raw views: the backend checks the paragraph under the
cursor, the writer picks a correction or adds a word to the document's glossary through the
response strip, and nothing is written to the file until the writer saves. A document's title,
author, and narrative perspective are edited in one modal, reachable from File → Edit → Document
or from Settings → Document for the open document.

The chapter list stays in step with the editor, keeping the shown chapter selected through list
changes and reading nothing when it is re-clicked. The File menu saves unsaved work before signing
out, and the identity line above the text shows a character's name parts or a chapter's title and
point of view. The window only sends text to the server and gets text back; it never touches files.
How files and the database work is in `README_markdown_redesign.md`, and login is in
`README_auth.md`.

## 1. Context and constraints

- **Thin client.** The editor talks only to the API. It never writes files or git; the backend is
  the only writer of record (`README_markdown_redesign.md` §3).
- **Platform.** Electron + TypeScript on PC (Linux/macOS/Windows) — the decided front-end platform
  (`README_markdown_redesign.md` §8). Mobile is out of scope; a future Flutter client would drive
  the same backend.
- **Existing API.** Editor operations map onto the document and chapter lifecycle
  endpoints; the document-edit dialog also reads the fixed perspective choices:
  - edit → `GET /api/chapters/{id}/document`
  - save → `PUT /api/chapters/{id}/document`
  - rename → `PUT /api/chapters/{id}` (title)
  - move → `POST /api/chapters/{id}/reorder` with `{after_chapter_id}` (`null` = first)
  - delete → `DELETE /api/chapters/{id}`
  - open document → `GET /api/documents/{id}`
  - edit document → `PUT /api/documents/{id}` (title, author, narrative perspective)
  - document attrs (Settings → Document) → `GET /api/documents/{id}/attrs` (attrs only, no hierarchy load)
  - perspective choices → `GET /api/documents/narrative-perspectives`
  - delete document → `DELETE /api/documents/{id}`
  The document-level renames and deletes additionally move or remove the document's
  owned store files (title-keyed directory and chapter markdown files) — backend-only
  work, invisible to the thin client (`README_markdown_redesign.md`, store README).
- **Editing state.** WYSIWYG and Raw MD are two views of the same canonical document; toggling Mode
  changes rendering, not the model behind the editor.

## 2. Window layout (decided)

```
┌───────────────────────────────────────────────────────────────────────────────┐
│  File ▾   Mode ▾   ⚙ ▾                                      [ –   ☐   ✕ ]    │
├──────────────────────┬──────────────────────────────────────────────┬────────┤
│ 📚 document ▾        │                                              │ ║      │
│   ▸ Act I ▾          │           E D I T   P A N E L                 │ ║ right│
│     · Chapter 1      │    WYSIWYG shown; Mode ▾ switches to Raw MD   │ │ 3px  │
│     · Chapter 2      │                                              │ ║ 10px │
│   ▾ Act II           │                                              │ ║ floor│
│     · Chapter 3      │              <same canonical doc>            │ ║ │││ ▓ │
│ ▕││▌◂ 7×13 grip      │                                              │ ║      │
│ ▕││││││▔ 3px seam    │                                              │ ║      │
│     · Chapter 4      │                                              │ ║      │
├──────────────────────┴──────────────────────────────────────────────┴────────┤
│ ▲ 3px seam, 13×7 grip ▹  ▔▔▔▔▔▔                                             │
│   one line of message… (drag up ⇧ grows scrollback console)                 │
└──────────────────────────────────────────────────────────────────────────────┘
```

Regions:

1. **Top menu bar** (in-window, full width): File, Mode, Settings (cog); the
   signed-in username sits at the right edge.
2. **Left panel**: document and chapter selector, resizable.
3. **Edit panel**: the bulk of the window; WYSIWYG or Raw MD source of the current chapter.
4. **Message panel**: one line by default, growable upward into a scrollback console.
5. **Far-right panel**: ten pixels wide by default, resizable open; placeholder for later features.

Regions 2–4 are separated by resize seams (below); the right panel stays on its own seam, kept at a
ten-pixel floor so the divider never vanishes.

### Resize handles (decided)

All seams use one parametric `ResizeHandle` component, orientation-parameterised:

- **Vertical seam** (left panel ↔ edit; edit ↔ right panel): a thin vertical line; in its centre a
  grip bulge holding **three vertical bars**. Dragging resizes both neighbours (one wider, the other
  narrower); cursor `ew-resize`.
- **Horizontal seam** (edit ⇕ message panel): the same component rotated 90° — a thin horizontal
  line, central 13-wide × 7-tall grip with **three horizontal bars**; cursor `ns-resize`.

Handles are always faintly visible, gain contrast on hover, and highlight while a drag is held. The
figure's numbers (~3px seam, ~7×13px grip) are **illustrative only**; real values come from the
visual spec. Every panel enforces a minimum size so no divider becomes impossible to grab:
`AppLayout` clamps each panel to at least 10px (the left chapter list stays at 120px minimum and the
message console at 24px minimum height), and the right panel starts at its 10px floor.

## 3. Menus (decided)

- **File ▾** — **Open** (the select-document modal, §8), **Import…** (pick a document directory
  and send it to `POST /api/import`), **Save** (current chapter;
  `PUT /api/chapters/{id}/document`), **Delete ▸ Document** (delete a whole document:
  pick it, confirm, then `DELETE /api/documents/{id}`; if it was the open document the
  editor and chapter list clear), **Edit ▸ Document / Chapter** (edit a document's
  title, author, and narrative perspective, or a chapter's title, saving through
  `PUT /api/documents/{id}` / `PUT /api/chapters/{id}`), **Sign out** (offer to save an unsaved buffer, end the session
  with `POST /api/auth/logout`, clear what the session owned, and show the gate again) and
  **Quit**.
- **Mode ▾** — **WYSIWYG** and **Raw MD**: switch the edit panel's view of the same document.
- **Settings ⚙▾** — a cog glyph instead of the word "Settings". **Document…** edits the
  currently open document through the same modal as File → Edit → Document; with no document
  open it says to open one first. **Language…** opens
  a dialog listing the proofreading languages the backend checker supports (`GET
  /api/check/languages`; the dialog falls back to its built-in list if that request fails),
  scrollable, current one marked, Cancel/Apply; choosing one sets the language used for backend
  spelling and grammar checks and the WYSIWYG editable's `lang` attribute. **Dictionary…** opens
  the document's glossary. The browser's own spellchecker is turned off, so the `lang` attribute
  no longer selects a native dictionary.

The menu bar is drawn in-window (HTML), not the native Electron menu, so its styling is ours and
stays identical across platforms; the native menu is removed at startup
(`Menu.setApplicationMenu(null)`), so the in-window bar is the only one.

## 4. Left panel: document and chapter selector (decided)

- Lists documents; each shows its chapters grouped under **act headers** (collapsible), with
  `Character` chapters in a **Characters** section after the acts. Group membership comes from
  each chapter's `act` and `category`: a chapter moved into a run of same-category chapters
  belonging to a different act adopts that act. A move cannot cross categories — the drop bar
  appears only inside the mover's category, and the server rejects a cross-category landing.
  Beyond the current document, other documents appear here too — place descriptions, world
  building, supporting research — to be defined later.
- Width is user-resizable via the vertical seam.
- Right-clicking a chapter opens the context menu: **Edit, Rename, Move, Renumber, POV, Delete**
  for a manuscript chapter; a character chapter drops **Move**, **Renumber**, and **POV** (they
  are not a manuscript's to move or number, and a character has no point of view). **POV** opens
  a name modal: the typed name is matched case-insensitively against the document's characters —
  one word against first name, then a nickname, then the surname; two words the first and
  surname in order; three or more the full name — and a near miss suggests a character
  (replacing the typed text, warning shown, the modal staying open). An empty name clears.
  (A metadata YAML entry is a later addition once per-chapter `*.yaml` meta files exist.)
- **Edit** — opens the chapter (`GET /api/chapters/{id}/document`) in the edit panel. Clicking the
  chapter already shown in the panel saves and reads nothing: the buffer stays as the writer
  left it, dirty or clean.
- **Rename** — a modal with a single field for the new name and **Cancel / Rename**.
- **Delete** — a confirmation modal first: **Cancel / Delete**.
- **Move** — enter move mode: a **solid bar** is drawn under the chapter name nearest the mouse.
  Moving to the bottom/top of the list scrolls it; the further above top (or below bottom) the mouse
  goes, the faster it scrolls, and the bar reappears under the newly revealed chapters. Clicking
  commits the move at that position (reorder via `after_chapter_id`); the chapter it lands next to
  determines the act it adopts (decided server-side) when that chapter is the same category.
  The bar is hidden, and a click does not commit, when the pointer is over the other category.
  **Esc** or a **click outside the list** cancels move mode.
- The chapter shown in the edit panel stays selected in the list: a reload after **Rename**,
  **Move**, **Renumber**, or **POV** keeps the selected row, while loading another document — or
  deleting the chapter — leaves nothing selected.

## 5. Edit panel (decided)

The central panel, taking up most of the window. It renders the current chapter's canonical text in
the selected Mode (WYSIWYG | Raw MD) and is where the interactive syntax checking from
`README_markdown_redesign.md` §7 is displayed: remark-lint structure diagnostics and backend
LanguageTool diagnostics, anchored to the sentence text as displayed, in both views, never part of
a save.

Both views edit the **same canonical document**: the text is the model, and toggling Mode changes
rendering, not the document behind the editor. The WYSIWYG is an editing surface, *not* a semantic
editor — the user types and edits prose in it (editing is allowed in either view), but nothing in
it restructures the document or the knowledge graph.

### Editor implementation (decided)

The Raw MD view is CodeMirror 6 (`@codemirror/lang-markdown`). The WYSIWYG view is ProseMirror
holding the canonical text as a paragraph-per-line document, with markdown-it heading detection
fed to node decorations — so Mode toggling never serializes text back out and the round trip is
byte-stable by construction. Spelling and grammar are checked by the backend (LanguageTool over
`POST /api/check`), not by the browser: native spellchecking is disabled, and the WYSIWYG
editable's `lang` attribute (default `en-US`) is the checker language plus accessibility
metadata, rewritten by the Settings → Language… dialog (§3). Span-aware highlighting of the
inline HTML (`data-par-id`,
`data-triple`, `data-spo`) and remark-lint diagnostics in the edit panel are still planned
(`README_markdown_redesign.md` §7). This supersedes the earlier open option "markdown-it + HTML,
or TipTap": TipTap was rejected because it is a structured-document (serializer-out) editor.

LanguageTool proofreading checks the paragraph holding the cursor, debounced at about 500 ms; the
focused sentence is the cursor's sentence. Diagnostics for other paragraphs are cleared, and a
reply whose paragraph has already changed is discarded. The squiggle shows the diagnostic's
severity. **Right-clicking a squiggle** asks in the response strip: a line naming the word and
its message, up to five replacements, and **Add to dictionary**. Choosing a replacement applies
it to the buffer — the writer's next
save is still the only write to the file — and adding a word stores it in *this document's*
glossary (`PUT /api/documents/{id}/glossary`), then re-checks; the word is not added to any
account-wide or LanguageTool dictionary. Right-clicking selected text that is not a diagnostic
keeps the existing quote actions in the same strip (§4).

In **Raw MD** the same rule reads the canonical paragraph holding the cursor: front matter and
the paragraph's span lines are skipped, inline span markup is stripped, HTML entities are
decoded, and each sentence line keeps the newline the writer sees. Diagnostics map back through
those offsets onto CodeMirror lint markers; right-clicking a marker opens the same strip actions,
and a replacement edits the canonical buffer in place.

**Decorations** are ProseMirror's mechanism for rendering over text without changing it. A
decoration applies a CSS class, style, or injected DOM element to a range of the flat document
text, keyed to document positions so it maps automatically as the user types. Three kinds suffice
here:

- **Inline decoration** — a class/style over a range of text (e.g. `em` over `*text*`, or a class
  over a `data-spo` span).
- **Node decoration** — attributes/class on a whole block node (e.g. styling one highlighted
  paragraph).
- **Widget decoration** — an extra DOM element at a position, not part of the text (e.g. a grip, a
  chip).

In Raw Mode the markdown markup is shown (`show-markup`); in WYSIWYG it is hidden (`hide-markup`) or
styled — the two views are the same document with different decorations.

### Paragraph-anchored operations (planned)

Paragraph identity already lives in the text (`data-par-id` spans), so paragraph-anchored oper-
ations reduce to locating an id in the buffer and decorating its range. The first planned example:

- **Find a paragraph by id and highlight it** — the editor finds the paragraph whose `data-par-id`
  matches, scrolls it into view, and highlights it (a decoration over its range, visible in both
  views). Clients include diagnostics jumping to a flagged sentence and the left-panel navigation.

This is one instance of a general paragraph-anchored find/highlight capability, kept cheap by the
text-is-the-model architecture; further instances are anticipated. The same identity mechanism
underlies cursor/view recovery after a save (`README_markdown_redesign.md` §5).

## 6. Message panel (decided)

A strip under the edit panel showing one line by default: the **chat box** alone. Dragging the
horizontal seam makes it taller, revealing a **scrollback console** of earlier messages above the
chat box. Its role is the console: save results (canonicalized, change summary), errors, and
delivered diagnostics — plus the AI chat history: a submitted prompt moves into the log as its
newest line and the model's reply follows it. From the first submit the panel holds a third
strip, the **response area**, between the log and the chat box: a spinner while the prompt is in
flight (the chat box collapses meanwhile), then the reply in the response syntax with its text
lines and buttons. The chat box is always a whole number of text lines high (about one third of
the panel by default, growing automatically as its typed text needs more lines); the console and
the response area scroll when their content outgrows the panel. `frontend/src/renderer/layout/README_response_area.md`
specifies the response syntax.

## 7. Right panel (read-only chapters)

Far right, now the mirror of the chapter list — the same default width, not the
10 px sliver. A tab strip across its top lists chapters shown read-only: the
writer-added ones first (kept until closed), then the characters the paragraph
under the cursor mentions (replaced as the cursor moves). The opened chapter is
the writer's markdown file rendered read-only — shown as-is when it exists,
hydrated from the graph only when it does not. The full spec, including the tab
truncation, the mention map that drives the automatic tabs, and the
response-area function that opens a chapter scrolled to a paragraph, is in
`frontend/src/renderer/layout/README_right_panel.md`.

## 8. Modals (decided)

- **Rename chapter** — name field + **Cancel / Rename**.
- **Delete confirmation** — "Are you sure you want to delete <chapter>?" with **Cancel / Delete**,
  shown before any delete runs.
- **Quit with changes** — when there are local (unsaved) changes: "Save chapter first?" with
  **Cancel / Discard / Save and Quit**.
- **Sign out with changes** — the same question, asked before the session ends rather than before
  the window closes: "Save chapter first?" with **Cancel / Discard / Save**. **Cancel** keeps the
  session and closes the dialog, **Discard** ends the session without saving, **Save** saves first
  and then ends it. A save that fails leaves the dialog's outcome unspent: the session survives and
  the buffer stays dirty, so nothing typed is lost to a failed write.
- **No last document on start** — a list to pick a document from, when app state has none.
- **Open document** (File → Open) — a scrollable list of documents by title, fetched from
  `GET /api/documents`. Clicking a row selects it and enables the **Open** button (disabled
  until a row is chosen); **Open** loads the chosen document, **Cancel** dismisses the modal.
- **Delete document** (File → Delete → Document) — the same scrollable list with **Cancel /
  Delete** (Delete disabled until a row is chosen). Picking a document and pressing **Delete**
  opens a second confirmation, "Are you sure you want to delete <title>?" with **Cancel /
  Delete**; only that second **Delete** calls `DELETE /api/documents/{id}`. If the deleted
  document was the one open in the editor, the editor and the chapter list clear
  (`PUT /api/app/state` forgets it as the last document).
- **Edit document** (File → Edit → Document) — the document list with **Cancel / Edit** (Edit
  disabled until a row is chosen). **Edit** opens a modal pre-filled with the chosen document's
  title, author, and narrative perspective; the perspective field is a select containing
  **None** and the codes from `GET /api/documents/narrative-perspectives`. The edited values
  stay in the modal until **Save** (disabled while the title is blank). **Save** sends all three
  fields via `PUT /api/documents/{id}` — which renames the document's store directory when the
  title changed — then reloads the chapter list; **Cancel** discards the edits. **Settings →
  Document…** opens the same modal for the open document without the picker; it reads only the
  document attrs (`GET /api/documents/{id}/attrs`) so the dialog does not wait on the full
  document, and when none is open it asks the writer to open one first.
- **Edit chapter** (File → Edit → Chapter) — a single title field pre-filled with the
  selected chapter's title and **Cancel / Save**. **Save** updates the title via
  `PUT /api/chapters/{id}` (renaming the chapter's store file) and reloads the chapter list;
  no modal appears when no chapter is selected.
- **Sign in** — always: `GET /api/auth/config` always reports `login_required: true`, so there
  is no mode in which the gate is skipped. The gate carries a **username / password form**, which
  posts to `POST /api/auth/login/password`. It is password-only: there are no provider buttons, so
  an account that exists only through OAuth has to be given a password by an administrator running
  `dockb users set-password` before it can open the editor. The backend's OAuth routes
  (`GET /api/auth/login?provider=…` and `/callback`) still work and are unchanged; only the editor
  stopped offering them. A first-time user on a temporary password is shown a **change your
  password** screen instead, and the manuscript routes answer 403
  `password_change_required` until they do (`README_auth.md` §7).

### Unsaved-change detection (decided)

"Local changes" for the Quit modal compares the editor text against the last **canonical** text the
backend returned — not against what the user most recently typed — because the canonical round trip
reformats. A menubar badge (`● Unsaved`) makes the state visible.

## 9. Start-up behaviour (decided)

On launch the editor asks `GET /api/auth/config`, which always reports `login_required: true`,
so the **Sign in** gate is always shown; the username comes from `GET /api/auth/me`, which also
reports `password_change_required`, and is shown in the menubar. Once signed in it restores the **last document**
from app state. If there is one, it loads the chapter list (panel widths and mode live in the
same state). If there is none, it shows the **select a document** modal. The state is stored
per-user on the backend: `GET/PUT /api/app/state` backed by the SQLite `app_state` table (see
`README_auth.md`).

Signing out returns here rather than closing anything: `File → Sign out` ends the session, clears
the chapter list, the editor buffer, the unsaved badge and the username in the menubar, and the next
pass begins again at the sign-in gate above. Cancelling that gate stops the editor instead — with no
session left, every request that pass would make is a guaranteed 401.

## 10. Resolved questions

The open questions in earlier revisions have been settled:

- **App state** — backend per-user `GET/PUT /api/app/state` over the SQLite `app_state` table
  (`README_auth.md`), not a local Electron `appData` file.
- **Acts** — grouping headers only, not model entities; membership comes from each chapter's `act`
  front-matter attribute, adopted server-side when a chapter is moved.
- **Message panel** — the console for save results, errors, delivered diagnostics, and the AI
  chat: prompts move into the rolling log, the model replies below them in the response syntax
  (`frontend/src/renderer/layout/README_response_area.md`).
- **Move-mode cancellation** — Esc or a click outside the list.
- **Menubar** — in-window (HTML), not the native Electron menu.