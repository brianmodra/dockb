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
`javascript:`, and other schemes) before calling Electron's `shell.openExternal`, and
a `quit` handler that calls `app.quit()`. The
preload (`src/main/preload.ts`) exposes them to the renderer as
`window.dockb.openExternal(url)` and `window.dockb.quit()` alongside `platform`. The login itself stays
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
  the message console, and is what `mountShell` renders. `setMode`,
  `restoreState`, and `panelWidths` give the shell a way to restore and persist
  the layout: the user's drags and mode picks are reported through
  `onWidthsChange`/`onMode`, and `restoreState` reapplies saved widths and
  mode. `setDirty` toggles a menubar badge (`● Unsaved`) when the editor has
  local changes. The `onSave`/`onQuit` options wire File → Save and File → Quit
  to the caller.
- `editPanel.ts` — the chapter edit surface: two views of the same canonical
  text. In raw mode a CodeMirror 6 view shows the markdown; in WYSIWYG mode a
  ProseMirror view (`wysiwyg.ts`) shows the prose. Toggling Mode re-syncs both
  views from the active buffer, so the text is never serialized out (UI README
  §5). `load` fetches a chapter document (`GET /api/chapters/{id}/document`)
  and records the returned text as the clean baseline; `save` PUTs the editor
  text and adopts the returned canonical text as the new baseline, so
  `isDirty()` is always *current buffer vs. last canonical* (UI README §8).
  `onDirtyChange` reports that flag whenever it flips, so the menubar badge
  can follow. Save results and load/save errors are reported through
  `onMessage`.
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
- `menubar.ts` — the in-window HTML menubar: **File** (Save → `onSave`, Quit →
  `onQuit`), **Mode** (WYSIWYG, Raw MD — reported through `onMode`), and
  **Settings** (⚙, General, a no-op).
- `chapterList.ts` — the chapter selector: chapters grouped into contiguous
  act runs (`groupByAct`), each under a collapsible header (empty act labelled
  "No act"); rows are selectable (`select`/click) and emit a context-menu
  signal on right-click.
- `contextMenu.ts` — the right-click menu; it renders items at the pointer,
  fires the chosen item's callback, and closes on an outside mousedown or Esc.
- `modals.ts` — promise-based in-window modals (`openModal`, `confirmModal`,
  `promptModal`) used by rename/delete, the quit-save choice, and the document
  picker; buttons resolve a value and remove the overlay.
- `documentPicker.ts` — `openDocumentPicker`: a modal listing the available
  documents (`listDocuments`), resolving with the chosen id or `null` on
  Cancel; shows an empty-state row when there are none and routes load failures
  through the error rule.
- `signInGate.ts` — `openSignInGate`: first-run modal with **Sign in** /
  **Cancel**. Sign in runs `login` (fetch the provider URL, open it in the
  system browser) then `checkSession`; a live session closes the gate, a
  missing session or a failed login is reported and the gate stays open so
  the user can retry after finishing consent in the browser.
- `state/appState.ts` — `AppStateController`: thin async wrapper over
  `GET/PUT /api/app/state` (`load`, `saveLastDocument`, `saveEditMode`,
  `savePanelWidths`). Load failures degrade to a blank state, save failures
  are logged and surfaced through `onMessage` — never thrown.
- `state/startup.ts` — `runStartup`: applies the saved panel widths and edit
  mode, then either loads the saved last document or opens the document
  picker when none is saved, loading the picked document if one is chosen.
- `state/quit.ts` — `quitApp`: quits immediately when the editor is clean;
  otherwise raises the "Save chapter first?" modal with **Cancel** /
  **Discard** / **Save and Quit**, saving (and bailing out if the save fails)
  before quitting.
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
panel through `onMessage`. This applies to load/save, rename, delete, move,
the app-state and document-list calls behind startup, and sign-in.

### Startup and quit

`mountShell` (in `src/renderer/main.ts`) wires the shell together: it renders
the layout, mounts the edit and left panels, and — when given an `ApiClient` —
checks the session first. No session opens the sign-in gate; cancelling it
leaves the shell idle. Once signed in it runs `runStartup` against the saved
app state so the user returns to their last
document, panel widths, and edit mode, or lands on the document picker when no
document is saved. The chosen document is remembered via
`saveLastDocument`. Mode picks and panel drags are persisted back through
`AppStateController`, and File → Save is wired to the edit panel. File → Quit
runs `quitApp`, which saves (after asking, when there are unsaved changes) and
then signals the main process over the `quit` IPC channel; `src/main/ipc.ts`
registers it to `app.quit()`.

## Layout

- `src/main/main.ts` — Electron main: creates a sandboxed, context-isolated
  `BrowserWindow`, loads the Vite dev server when `VITE_DEV_SERVER_URL` is set,
  otherwise the built `dist/index.html`.
- `src/main/preload.ts` — contextBridge preload exposing `window.dockb` with
  `platform`, `openExternal` (invoke over the `open-external` channel), and
  `quit` (send over the `quit` channel).
- `src/renderer/` — renderer entry (`main.ts` mounts the shell; `mountShell`
  accepts an optional `ApiClient` and drives startup and quit as described
  above); `api/` holds the typed backend client and session/login helpers;
  `log.ts` holds the shared error reporter.
- `vite.config.mts` — Vite/Vitest config with the :3000 dev server and `/api`
  proxy.
- `tests/` — Vitest tests for the config, the shell, and the Electron main.