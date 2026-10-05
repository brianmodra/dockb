# Markdown Editor UI Design

## Executive Summary

This is the design of DockB's writing window. It explains the menus, the chapter list, the editor, and the dialogs, so someone new can see what the writer sees and why each click does what it does.

The window only sends text to the server and gets text back. It never touches files. How the files and the database work is in `README_markdown_redesign.md`. Login is in `README_auth.md`.

## 1. Context and constraints

- **Thin client.** The editor talks only to the API. It never writes files or git; the backend is
  the only writer of record (`README_markdown_redesign.md` §3).
- **Platform.** Electron + TypeScript on PC (Linux/macOS/Windows) — the decided front-end platform
  (`README_markdown_redesign.md` §8). Mobile is out of scope; a future Flutter client would drive
  the same backend.
- **Existing API.** All editor operations map onto the document and chapter lifecycle
  endpoints, so the UI design implies no backend work:
  - edit → `GET /api/chapters/{id}/document`
  - save → `PUT /api/chapters/{id}/document`
  - rename → `PUT /api/chapters/{id}` (title)
  - move → `POST /api/chapters/{id}/reorder` with `{after_chapter_id}` (`null` = first)
  - delete → `DELETE /api/chapters/{id}`
  - open document → `GET /api/documents/{id}`
  - edit document → `PUT /api/documents/{id}` (title, author)
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

- **File ▾** — **Open** (the select-document modal, §8), **Save** (current chapter;
  `PUT /api/chapters/{id}/document`), **Delete ▸ Document** (delete a whole document:
  pick it, confirm, then `DELETE /api/documents/{id}`; if it was the open document the
  editor and chapter list clear), **Edit ▸ Document / Chapter** (edit a document's
  title/author or a chapter's title, saving through `PUT /api/documents/{id}` /
  `PUT /api/chapters/{id}`) and **Quit**.
- **Mode ▾** — **WYSIWYG** and **Raw MD**: switch the edit panel's view of the same document.
- **Settings ⚙▾** — a cog glyph instead of the word "Settings". One item, **Language…**: opens
  a dialog listing spellcheck languages (scrollable, current one marked, Cancel/Apply); choosing
  one sets the `lang` attribute on the WYSIWYG editable so the browser's native spelling uses
  that dictionary.

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
- Right-clicking a chapter opens the context menu: **Edit, Rename, Move, Delete**. (A metadata YAML
  entry is a later addition once per-chapter `*.yaml` meta files exist.)
- **Edit** — opens the chapter (`GET /api/chapters/{id}/document`) in the edit panel.
- **Rename** — a modal with a single field for the new name and **Cancel / Rename**.
- **Delete** — a confirmation modal first: **Cancel / Delete**.
- **Move** — enter move mode: a **solid bar** is drawn under the chapter name nearest the mouse.
  Moving to the bottom/top of the list scrolls it; the further above top (or below bottom) the mouse
  goes, the faster it scrolls, and the bar reappears under the newly revealed chapters. Clicking
  commits the move at that position (reorder via `after_chapter_id`); the chapter it lands next to
  determines the act it adopts (decided server-side) when that chapter is the same category.
  The bar is hidden, and a click does not commit, when the pointer is over the other category.
  **Esc** or a **click outside the list** cancels move mode.

## 5. Edit panel (decided)

The central panel, taking up most of the window. It renders the current chapter's canonical text in
the selected Mode (WYSIWYG | Raw MD) and is where the interactive syntax checking from
`README_markdown_redesign.md` §7 is displayed: remark-lint structure diagnostics and backend
prose/NLP diagnostics, anchored to the sentence text as displayed, in both views, never part of a
save.

Both views edit the **same canonical document**: the text is the model, and toggling Mode changes
rendering, not the document behind the editor. The WYSIWYG is an editing surface, *not* a semantic
editor — the user types and edits prose in it (editing is allowed in either view), but nothing in
it restructures the document or the knowledge graph.

### Editor implementation (decided)

The Raw MD view is CodeMirror 6 (`@codemirror/lang-markdown`). The WYSIWYG view is ProseMirror
holding the canonical text as a paragraph-per-line document, with markdown-it heading detection
fed to node decorations — so Mode toggling never serializes text back out and the round trip is
byte-stable by construction. Spellcheck is the browser's native engine: the WYSIWYG editable
carries a `lang` attribute (default `en-US`), which the Settings → Language… dialog (§3) rewrites
to select the dictionary. Span-aware highlighting of the inline HTML (`data-par-id`,
`data-triple`, `data-spo`) and remark-lint / NLP diagnostics in the edit panel are still planned
(`README_markdown_redesign.md` §7). This supersedes the earlier open option "markdown-it + HTML,
or TipTap": TipTap was rejected because it is a structured-document (serializer-out) editor.

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

A strip under the edit panel showing one line of text by default. Dragging the horizontal seam makes
it taller, revealing a **scrollback console** of earlier messages. Its role is the console: save
results (canonicalized, change summary), errors, and delivered diagnostics — plus further message
kinds to be designed later.

## 7. Right panel (decided shape, no role yet)

Far right, ten pixels wide by default, opened by dragging its seam. Purpose reserved for later
features (undecided).

## 8. Modals (decided)

- **Rename chapter** — name field + **Cancel / Rename**.
- **Delete confirmation** — "Are you sure you want to delete <chapter>?" with **Cancel / Delete**,
  shown before any delete runs.
- **Quit with changes** — when there are local (unsaved) changes: "Save chapter first?" with
  **Cancel / Discard / Save and Quit**.
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
  disabled until a row is chosen). **Edit** opens a two-field modal pre-filled with the chosen
  document's title and author; the edited values stay in the modal until **Save** (disabled
  while the title is blank). **Save** updates via `PUT /api/documents/{id}` — which renames
  the document's store directory when the title changed — then reloads the chapter list;
  **Cancel** discards the edits. The modal edits title and author only; any other metadata
  fields are preserved untouched, not shown, and not sent.
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

## 10. Resolved questions

The open questions in earlier revisions have been settled:

- **App state** — backend per-user `GET/PUT /api/app/state` over the SQLite `app_state` table
  (`README_auth.md`), not a local Electron `appData` file.
- **Acts** — grouping headers only, not model entities; membership comes from each chapter's `act`
  front-matter attribute, adopted server-side when a chapter is moved.
- **Message panel** — the console for save results, errors, and delivered diagnostics, plus further
  message kinds to be designed later.
- **Move-mode cancellation** — Esc or a click outside the list.
- **Menubar** — in-window (HTML), not the native Electron menu.