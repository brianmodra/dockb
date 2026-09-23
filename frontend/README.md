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

## Layout

- `src/main/main.ts` — Electron main: creates a sandboxed, context-isolated
  `BrowserWindow`, loads the Vite dev server when `VITE_DEV_SERVER_URL` is set,
  otherwise the built `dist/index.html`.
- `src/main/preload.ts` — contextBridge preload (currently exposes platform).
- `src/renderer/` — renderer entry that mounts the shell window; `api/` holds
  the typed backend client and session/login helpers.
- `vite.config.mts` — Vite/Vitest config with the :3000 dev server and `/api`
  proxy.
- `tests/` — Vitest tests for the config, the shell, and the Electron main.