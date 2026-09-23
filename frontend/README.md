# DockB Frontend

## Executive Summary

This directory holds DockB's desktop editor: an Electron + TypeScript thin
client that talks only to the backend API. It replaces the removed React +
Tiptap editor. The layout, menus, panel resize seams, and modals are specified
in `../README_markdown_editor_ui.md`; the markdown redesign it edits is
`../README_markdown_redesign.md`.

The stack is Vite + TypeScript (renderer), Electron (shell), Vitest (tests),
and ESLint (lint). The dev server runs on :3000 and proxies `/api` to the
backend on :8000, keeping the editor file-and-disk-free. The editor's app
state and identity come from backend endpoints (`README_auth.md`), not local
files.

## API client and session

The renderer talks to the backend through a typed client in
`src/renderer/api/`: `client.ts` (document/chapter CRUD, the chapter document
lifecycle — `GET/PUT /api/chapters/{id}/document` — reorder, app state, and
auth helpers), `http.ts` (fetch wrapper that surfaces non-2xx responses as
`ApiError`), and `session.ts` (`checkSession` via `GET /api/auth/me`, and
`login`, which fetches the provider's authorization URL and opens it in the
system browser).

Opening the system browser crosses the Electron sandbox boundary through a
single vetted IPC channel. `src/main/ipc.ts` registers an `open-external`
handler that accepts **only** `http:`/`https:` URLs (rejecting `file:`,
`javascript:`, and other schemes) before calling Electron's `shell.openExternal`; the
preload (`src/main/preload.ts`) exposes it to the renderer as
`window.dockb.openExternal(url)` alongside `platform`. The login itself stays
server-side (see `README_auth.md` §6): the backend exchanges the code and sets
the HttpOnly session cookie, which the client presents on every API call.

## Commands

Run these from `frontend/`:

- `npm run dev` — Vite dev server on :3000, proxying `/api` to :8000.
- `npm run build` — type-check (`tsc`) and build the renderer (`vite build`)
  and the Electron main/preload (`tsc -p tsconfig.node.json`).
- `npm test` — Vitest run (jsdom).
- `npm run lint` — ESLint.
- `npm start` — run the built Electron app (`electron .`).

## Window layout

The editor shell lives in `src/renderer/layout/` and matches
`../README_markdown_editor_ui.md` §2–§5:

- `layout.ts` — `AppLayout`: assembles the in-window menubar above a main row
  (left panel, edit panel, right panel) over the message panel. It owns the
  panel widths and the edit Mode (WYSIWYG | Raw MD), exposes `pushMessage` for
  the message console, and is what `mountShell` renders. The `onSave` option
  wires the File → Save menu item to the caller.
- `editPanel.ts` — the chapter edit surface: two views of the same canonical
  text. In raw mode a CodeMirror 6 view shows the markdown; in WYSIWYG mode a
  ProseMirror view (`wysiwyg.ts`) shows the prose. Toggling Mode re-syncs both
  views from the active buffer, so the text is never serialized out (UI README
  §5). `load` fetches a chapter document (`GET /api/chapters/{id}/document`)
  and records the returned text as the clean baseline; `save` PUTs the editor
  text and adopts the returned canonical text as the new baseline, so
  `isDirty()` is always *current buffer vs. last canonical* (UI README §8).
  Save results and load/save errors are reported through `onMessage`.
- `wysiwyg.ts` — the WYSIWYG view: a ProseMirror editor holding the canonical
  text as a paragraph-per-line document (byte-stable round trip by
  construction, no serializer), with markdown-it heading detection fed to a
  node decoration that styles heading paragraphs. Edits flow back through
  `onChange`; `setContent`/`content` round-trip the buffer byte-for-byte.
- `ResizeHandle.ts` — the single parametric seam component: vertical
  (left↔edit, edit↔right, `ew-resize`) or horizontal (edit⇕message,
  `ns-resize`), each with a grip of three bars, faint by default, gaining
  contrast on hover and highlighting while a drag is held. It reports pixel
  deltas to the layout, which enforces minima (left panel ≥ 120px) and keeps
  the right panel grippable from its zero-width default.
- `menubar.ts` — the in-window HTML menubar: **File** (Save → `onSave`, Quit),
  **Mode** (WYSIWYG, Raw MD — reported to the layout, which forwards it to the
  edit panel's `setMode`), **Settings** (⚙, General, a no-op). Quit is wired
  to the quit flow in section 9; here it renders.
- `chapterList.ts` — the chapter selector: chapters grouped into contiguous
  act runs (`groupByAct`), each under a collapsible header (empty act labelled
  "No act"); rows are selectable (`select`/click) and emit a context-menu
  signal on right-click.
- `contextMenu.ts` — the right-click menu; it renders items at the pointer,
  fires the chosen item's callback, and closes on an outside mousedown or Esc.
- `modals.ts` — promise-based in-window modals (`openModal`, `confirmModal`,
  `promptModal`) used by rename/delete here and by the quit and document
  picker in section 9; buttons resolve a value and remove the overlay.
- `moveMode.ts` — the Move drop-bar interaction: `MoveMode` draws a bar under
  the chapter nearest the pointer, auto-scrolls when the pointer crosses the
  list edges, commits the reorder via `reorderChapter` on a within-list click,
  and cancels on Esc or an outside click. `computeAfterForY` maps a pointer
  Y to the nearest chapter slot (above the first midpoint → null = move to
  front).
- `leftPanel.ts` — `LeftPanel` ties it together: loads a document's chapters
  through `listChapters`, wires the context menu to **Edit** (open chapter),
  **Rename** (prompt modal → `updateChapter`), **Delete** (confirm →
  `deleteChapter`), and **Move** (`MoveMode` → `reorderChapter`), reloading the
  list after each mutation.

Panels are plain elements built with `createElement`/`textContent` — no user
data ever enters the DOM as HTML.

### Error reporting

All user-facing failures follow one rule: report to the terminal log (via
`console.error` in `log.ts`'s `reportError`) **and** to the bottom message
panel through `onMessage`. This applies to load/save, rename, delete, and move.

## Layout

- `src/main/main.ts` — Electron main: creates a sandboxed, context-isolated
  `BrowserWindow`, loads the Vite dev server when `VITE_DEV_SERVER_URL` is set,
  otherwise the built `dist/index.html`.
- `src/main/preload.ts` — contextBridge preload (currently exposes
  `window.dockb` platform + `openExternal`).
- `src/renderer/` — renderer entry (`main.ts` mounts the shell; `mountShell`
  accepts an optional `ApiClient` + document id to populate the left panel and
  the edit panel); `api/` holds the typed backend client and session/login
  helpers; `log.ts` holds the shared error reporter.
- `vite.config.mts` — Vite/Vitest config with the :3000 dev server and `/api`
  proxy.
- `tests/` — Vitest tests for the config, the shell, and the Electron main.