# Markdown Editor UI Design

## Executive Summary

This document records the UI design for DockB's new front end: an Electron + TypeScript markdown
editor that replaces the removed React + Tiptap editor. It is the thin client of the markdown
redesign (see `README_markdown_redesign.md`): it sends raw text and receives canonical text, and
never touches files, git, services, or repositories. The layout is a top menubar over an edit panel
flanked by a resizable left document/chapter selector and a far-right panel that starts at zero
width, with a bottom message console. The edit panel toggles between WYSIWYG and raw markdown views
of the same canonical document. Chapters are managed from the left column via a right-click context
menu — edit, rename, move (a drop-bar interaction), delete (with confirmation) — the menubar carries
File (save, quit), Mode (view toggle) and a cog Settings menu, and startup restores the last
document when app state has one, otherwise prompts for one.

This document records the decisions — the window layout, the in-window menubar, the parametric
resize-handle component, the modals, the interaction patterns — and the questions still open (where
app state lives, whether acts are grouping headers or model entities, the message panel's exact
role). The backend story and the canonical format live in `README_markdown_redesign.md`; this
document is only about the editor's shape and interactions.

## 1. Context and constraints

- **Thin client.** The editor talks only to the API. It never writes files or git; the backend is
  the only writer of record (`README_markdown_redesign.md` §3).
- **Platform.** Electron + TypeScript on PC (Linux/macOS/Windows) — the decided front-end platform
  (`README_markdown_redesign.md` §8). Mobile is out of scope; a future Flutter client would drive
  the same backend.
- **Existing API.** All editor operations map onto the document lifecycle endpoints, so the UI
  design implies no backend work:
  - edit → `GET /api/chapters/{id}/document`
  - save → `PUT /api/chapters/{id}/document`
  - rename → `PUT /api/chapters/{id}` (title)
  - move → `POST /api/chapters` with `after_chapter_id` (reorders via `index`)
  - delete → `DELETE /api/chapters/{id}`
  - open document → `GET /api/documents/{id}`
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
│     · Chapter 2      │                                              │ ║ 0-w  │
│   ▾ Act II           │                                              │ ║      │
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

1. **Top menu bar** (in-window, full width): File, Mode, Settings (cog).
2. **Left panel**: document and chapter selector, resizable.
3. **Edit panel**: the bulk of the window; WYSIWYG or Raw MD source of the current chapter.
4. **Message panel**: one line by default, growable upward into a scrollback console.
5. **Far-right panel**: zero width by default, resizable open; placeholder for later features.

Regions 2–4 are separated by resize seams (below); the right panel sits on its own seam so it stays
grippable at zero width.

### Resize handles (decided)

All seams use one parametric `ResizeHandle` component, orientation-parameterised:

- **Vertical seam** (left panel ↔ edit; edit ↔ right panel): a thin vertical line; in its centre a
  grip bulge holding **three vertical bars**. Dragging resizes both neighbours (one wider, the other
  narrower); cursor `ew-resize`.
- **Horizontal seam** (edit ⇕ message panel): the same component rotated 90° — a thin horizontal
  line, central 13-wide × 7-tall grip with **three horizontal bars**; cursor `ns-resize`.

Handles are always faintly visible, gain contrast on hover, and highlight while a drag is held. The
figure's numbers (~3px seam, ~7×13px grip) are **illustrative only**; real values come from the
visual spec. Adjacent panels enforce minimum sizes (left panel min-width, message-panel ceiling),
and the right panel's seam stays available even at zero width.

## 3. Menus (decided)

- **File ▾** — **Save** (current chapter; `PUT /api/chapters/{id}/document`) and **Quit**.
- **Mode ▾** — **WYSIWYG** and **Raw MD**: switch the edit panel's view of the same document.
- **Settings ⚙▾** — a cog glyph instead of the word "Settings". One item, **General**; it will
  later open a modal, currently it does nothing.

The menu bar is drawn in-window (HTML), not the native Electron menu, so its styling is ours and
stays identical across platforms.

## 4. Left panel: document and chapter selector (decided)

- Lists documents; each shows its chapters grouped under **act headers** (collapsible). Beyond the
  current document, other documents appear here too — character descriptions, place descriptions,
  world building, supporting research — to be defined later.
- Width is user-resizable via the vertical seam.
- Right-clicking a chapter opens the context menu: **Edit, Rename, Move, Delete**. (A metadata YAML
  entry is a later addition once per-chapter `*.yaml` meta files exist.)
- **Edit** — opens the chapter (`GET /api/chapters/{id}/document`) in the edit panel.
- **Rename** — a modal with a single field for the new name and **Cancel / Rename**.
- **Delete** — a confirmation modal first: **Cancel / Delete**.
- **Move** — enter move mode: a **solid bar** is drawn under the chapter name nearest the mouse.
  Moving to the bottom/top of the list scrolls it; the further above top (or below bottom) the mouse
  goes, the faster it scrolls, and the bar reappears under the newly revealed chapters. Clicking
  commits the move at that position (reorder via `after_chapter_id`). Esc cancels move mode (see
  **Open questions**).

## 5. Edit panel (decided)

The central panel, taking up most of the window. It renders the current chapter's canonical text in
the selected Mode (WYSIWYG | Raw MD) and is where the interactive syntax checking from
`README_markdown_redesign.md` §7 is displayed: remark-lint structure diagnostics and backend
prose/NLP diagnostics, anchored to the sentence text as displayed, in both views, never part of a
save.

(The editor rendering itself — CodeMirror 6 source mode, the WYSIWYG renderer, the span-aware
language extension — is the editor implementation, decided at `README_markdown_redesign.md` §8.)

## 6. Message panel (decided shape, role to confirm)

A strip under the edit panel showing one line of text by default. Dragging the horizontal seam makes
it taller, revealing a **scrollback console** of earlier messages. Intended home: save results
(canonicalized, change summary), errors, and delivered diagnostics. The exact message set is yet to
confirm (see **Open questions**).

## 7. Right panel (decided shape, no role yet)

Far right, zero width by default, opened by dragging its seam. Purpose reserved for later features
(undecided).

## 8. Modals (decided)

- **Rename chapter** — name field + **Cancel / Rename**.
- **Delete confirmation** — "Are you sure you want to delete <chapter>?" with **Cancel / Delete**,
  shown before any delete runs.
- **Quit with changes** — when there are local (unsaved) changes: "Save <chapter> first?" with
  **Cancel / Discard / Save and Quit**.
- **No last document on start** — a list to pick a document from, when app state has none.

### Unsaved-change detection (decided)

"Local changes" for the Quit modal compares the editor text against the last **canonical** text the
backend returned — not against what the user most recently typed — because the canonical round trip
reformats. A visual dirty indicator on the chapter row (and/or menubar) makes the state visible.

## 9. Start-up behaviour (decided)

On launch the editor restores the **last document** from app state. If there is one, it `GET`s the
document and restores the chapter list (panel widths and mode live in the same state). If there is
none, it shows the **select a document** modal first. Where that state lives is open (below).

## 10. Open questions before trust

1. **Where app state lives** (last document, panel widths, current mode). Recommended: a small
   backend endpoint (per-user `GET/PUT /api/app/state`), keeping the editor file-and-disk-free and
   the state following the user; the alternative is a local Electron `appData` JSON. Settle before
   the state store is built.
2. **Acts: grouping only, or model entities?** The backend orders chapters flat (`index` /
   `after_chapter_id`); there is no act in the model. Decide whether acts are just collapsible
   headers (recommended initially) — and if so, whether a move across an act boundary is simply an
   order change across the boundary or is restricted.
3. **Message panel message set** — confirm it is the console for save results, errors, and async
   diagnostics.
4. **Move-mode cancellation** — Esc to cancel is proposed; confirm, and whether clicking outside the
   list also cancels.
5. **Menubar placement** — in-window (HTML) is decided; a native Electron menu is the rejected
   alternative (it cannot carry our styling). Recorded here so the choice is not revisited silently.