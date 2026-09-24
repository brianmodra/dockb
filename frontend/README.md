# DockB Frontend

## Executive Summary

This is DockB's desktop editor: an Electron app that talks only to the backend
API. Writers sign in, open a document, and edit a chapter in WYSIWYG or raw
markdown. The editor never writes files or git; save and restore go through
the API. How the window should look is in `../README_markdown_editor_ui.md`.

Commands (`npm run dev`, `npm test`, `npm run build`) live below. App state
and login come from the backend (`README_auth.md`), not from files on disk.

## API client and session

The renderer talks to the backend through a typed client in
`src/renderer/api/`: `client.ts` (documents, chapters, chapter-document
lifecycle, reorder, app state, auth), `http.ts` (`ApiError` on non-2xx), and
`session.ts` (`checkSession`, `login`).

Opening the system browser crosses the Electron sandbox through one vetted IPC
channel. `src/main/ipc.ts` accepts **only** `http:`/`https:` URLs on
`open-external` (rejecting `file:`, `javascript:`, and other schemes) and
registers `quit` to `app.quit()`. The preload exposes them as
`window.dockb.openExternal` and `window.dockb.quit`. Login stays server-side
(`README_auth.md` §6): the backend sets the HttpOnly session cookie.

## Commands

Run these from `frontend/`:

- `npm run dev` — Vite dev server on :3000, proxying `/api` to :8000.
- `npm run build` — type-check (`tsc`) and build the renderer (`vite build`)
  and the Electron main/preload (`tsc -p tsconfig.node.json`).
- `npm test` — Vitest run (jsdom).
- `npm run lint` — ESLint.
- `npm start` — run the built Electron app (`electron .`).

## Window layout

The shell lives in `src/renderer/layout/` and matches
`../README_markdown_editor_ui.md`. Modules:

- `layout.ts` — window chrome, panel seams, mode, dirty badge, menubar username
  label, message sink.
- `editPanel.ts` / `wysiwyg.ts` — CodeMirror raw and ProseMirror WYSIWYG views
  of the same canonical buffer; dirty = buffer vs last canonical.
- `menubar.ts` — File (Save, Quit), Mode, Settings.
- `leftPanel.ts` — chapter list, context menu, rename/delete/move.
- `documentPicker.ts`, `signInGate.ts`, `modals.ts` — start-up and confirm
  dialogs.
- `state/` — app-state persistence, start-up restore, quit-with-save.

Panels are built with `createElement`/`textContent` — no user data enters the
DOM as HTML.

### Error reporting

All user-facing failures go to the terminal log (`log.ts` `reportError`) **and**
the message panel (`onMessage`).

### Startup and quit

`mountShell` checks the session, then either the sign-in gate or
`runStartup` (restore last document, or pick one), and shows the signed-in
username in the menubar. Mode, panel widths, and last document persist via
`GET/PUT /api/app/state`. File → Quit asks to save when dirty, then sends the
`quit` IPC channel.

## Layout

- `src/main/main.ts` — sandboxed `BrowserWindow`; Vite URL or `dist/index.html`.
- `src/main/preload.ts` — `window.dockb` (`platform`, `openExternal`, `quit`).
- `src/renderer/` — `main.ts` mounts the shell; `api/` is the backend client.
- `vite.config.mts` — Vite/Vitest, :3000, `/api` proxy.
- `tests/` — Vitest (jsdom).
