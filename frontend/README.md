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
`session.ts` (`checkSession`, `login`). `index.ts` wires the client into
`mountShell`: its API base is a `VITE_API_BASE` build-time override if set,
else `http://localhost:8000/api` when the built shell is loaded from a `file://`
origin, else the relative `/api` (served by the Vite proxy). The backend must
allow that cross-origin shell in (`app_factory.py` CORS allows the `null`
file:// origin and the Vite dev origins).

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

Panels keep the dividers grippable: `layout.ts` clamps every panel to a 10px
minimum (left panel 120px, message console 24px) and the right panel starts at
its 10px floor.

- `layout.ts` — window chrome, panel seams, mode, dirty badge, menubar username
  label, message sink.
- `editPanel.ts` / `wysiwyg.ts` — CodeMirror raw and ProseMirror WYSIWYG views
  of the same canonical buffer; dirty = buffer vs last canonical. The raw view
  shows the canonical file as stored (YAML front matter and `<span>` markup
  intact); the WYSIWYG view derives its display from `chapterBody` (front
  matter and span tags removed, entities unescaped), so it never shows markup
  HTML. Save emits canonical form: the front matter is kept verbatim and each
  paragraph is re-wrapped in its `<span data-par-id>` (ids are carried in the
  paragraph attrs; a duplicated id falls back to a span-free paragraph).
  `plainContent()` returns the loose body, which is what the dirty check
  compares against the loaded canonical — changed text is dirty, a different
  id assignment alone is not. Switching modes while clean restores the
  canonical text; a dirty buffer is carried over as typed.

  The WYSIWYG renders each paragraph span as one block: sentence lines are
  joined with a single space (`wysiwyg-sb` mark) so they wrap together, a
  trailing backslash hides the escape and keeps the line break (`hardBreak`),
  and the blank-line paragraph delimiter shows as a single line gap. Paragraphs
  carry their preceding blank-line count in `blanksBefore`, so
  `bufferToDoc`/`docToString` round-trip the buffer byte-for-byte until an
  edit.

Panels are built with `createElement`/`textContent` — no user data enters the
DOM as HTML.
- `menubar.ts` — File (Open, Save, Quit), Mode, Settings; dropdowns dismiss on
  outside click or Esc.
- `leftPanel.ts` — chapter list, context menu, rename/delete/move. Clicking a
  chapter selects it **and** loads its text into the editor (via `onEdit` → the
  `.../document` GET).
- `documentPicker.ts`, `signInGate.ts`, `modals.ts` — start-up and confirm
  dialogs.
- `state/` — app-state persistence, start-up restore, quit-with-save.

Panels are built with `createElement`/`textContent` — no user data enters the
DOM as HTML.

### Error reporting

All user-facing failures go to the terminal log (`log.ts` `reportError`) **and**
the message panel (`onMessage`).

### Startup and quit

`mountShell` asks `GET /api/auth/config` and opens the sign-in gate only when
login is required (an OAuth provider is configured); in local mode it reads the
OS username from `/api/auth/me` and shows it in the menubar. Then it runs
`runStartup` (restore last document, or pick one); File → Open opens the same
select-document picker (`documentPicker.ts`
`openDocumentPickerConfirm`) and loads the chosen document. Mode, panel
widths, and last document persist via `GET/PUT /api/app/state`. File → Quit
asks to save when dirty, then sends the `quit` IPC channel.

## Layout

- `src/main/main.ts` — sandboxed `BrowserWindow`; removes the default Electron
  menu (`Menu.setApplicationMenu(null)`); Vite URL or `dist/index.html`.
- `src/main/preload.ts` — `window.dockb` (`platform`, `openExternal`, `quit`).
- `src/renderer/` — `index.ts` wires the `ApiClient` and mounts the shell;
  `main.ts` builds it; `api/` is the backend client.
- `vite.config.mts` — Vite/Vitest, :3000, `/api` proxy.
- `tests/` — Vitest (jsdom).
