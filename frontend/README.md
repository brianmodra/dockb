# DockB Frontend

## Executive Summary

This is DockB's desktop editor. It is a window that talks only to the server: sign in, open a document, and edit a chapter. It never writes files itself. The window does not even load its own interface from disk — the backend serves it, so the app and the API share an origin and the signed-in session reaches every route.

Read it to run the app and to find which file owns the chapter list, the editor, and login. How the window should look is in `../README_markdown_editor_ui.md`.

## API client and session

The renderer is served **by the backend** at `/editor/`, not loaded from a local file. `src/main/main.ts`
builds that URL from `DOCKB_API_ORIGIN` (default `http://localhost:8000`) and loads it with
`loadURL`; when `VITE_DEV_SERVER_URL` is set it loads that instead, so `npm run dev` is unchanged.
Being same-origin with the API is what lets the `SameSite=lax` session cookie reach the gated
routes and removes the need for both `credentials: "include"` and any CORS grant. `README_auth.md`
§4 has the reasoning.

The renderer talks to the backend through a typed client in
`src/renderer/api/`: `client.ts` (documents, chapters, chapter-document
lifecycle, reorder, app state, auth), `http.ts` (`ApiError` on non-2xx), and
`session.ts` (`checkSession`, `login`). `index.ts` wires the client into
`mountShell`: its API base is the relative `/api`, unless a `VITE_API_BASE`
build-time override is set.

Opening the system browser crosses the Electron sandbox through one vetted IPC
channel. `src/main/ipc.ts` accepts **only** `http:`/`https:` URLs on
`open-external` (rejecting `file:`, `javascript:`, and other schemes) and
registers `quit` to `app.quit()`. The preload exposes them as
`window.dockb.openExternal` and `window.dockb.quit`. Login stays server-side
(`README_auth.md` §6): the backend sets the HttpOnly session cookie.

The preload also exposes `window.dockb.getPathForFile`, `webUtils.getPathForFile`
by way of it, which is how the renderer learns the absolute path of a file the
user chose in a native dialog. Electron 32 removed `File.path`, so this is the
supported way to get one. It is the renderer's only route to a filesystem path, it
returns an empty string for a `File` not backed by disk so it cannot be used to
probe arbitrary paths, and a compromised renderer could learn the path of any file
the user picks — the user reviewed and accepted that.

### Multipart requests

`http.ts` labels a body `Content-Type: application/json` unless it is a
`FormData`, which is sent with no `Content-Type` at all so the browser can write
the multipart boundary itself. A header the caller sets explicitly still wins, so
the rule is only about the default. Every other body type stays on the JSON
default; `importDocument` is the only caller that sends `FormData`.

## Commands

Run these from `frontend/`:

- `npm run dev` — Vite dev server on :3000, proxying `/api` to :8000.
- `npm run build` — type-check (`tsc`) and build the renderer (`vite build`)
  and the Electron main/preload (`tsc -p tsconfig.node.json`).
- `npm test` — Vitest run (jsdom).
- `npm run lint` — ESLint.
- `npm start` — run the built Electron app (`electron .`). The backend must already be serving
  on `:8000`; the window loads the shell from it, not from disk.

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
  edit. The editable carries a `lang` attribute (default `en-US`), rewritten by
  the Settings → Language… dialog, which selects the browser spellcheck dictionary.

Panels are built with `createElement`/`textContent` — no user data enters the
DOM as HTML.
- `menubar.ts` — File (Open, Save, Delete ▸ Document, Edit ▸ Document/Chapter, Quit), Mode,
  Settings (Language… dialog); dropdowns and nested submenus dismiss on outside click or Esc.
- `leftPanel.ts` — chapter list, context menu, rename/delete/move. Manuscript
  chapters group under act headers; `Character` chapters sit in a Characters
  section after the acts. Move only offers drop slots inside the mover's
  category. Clicking a chapter selects it **and** loads its text into the editor
  (via `onEdit` → the `.../document` GET). Exposes the selected chapter and a
  reload that keeps the selection.
- `documentPicker.ts`, `signInGate.ts`, `modals.ts` — start-up, confirm and
  document-edit dialogs (the delete/edit-document flows live in `main.ts`).
- `languageSettings.ts` — the Language dialog (Settings ⚙ → Language…): a
  scrollable spellcheck-language list with Cancel/Apply; the chosen code is
  applied via `EditPanel.setLanguage`.
- `state/` — app-state persistence, start-up restore, quit-with-save.

### Error reporting

All user-facing failures go to the terminal log (`log.ts` `reportError`) **and**
the message panel (`onMessage`).

### Startup and quit

`mountShell` asks `GET /api/auth/config` and opens the sign-in gate only when
login is required (an OAuth provider is configured); in local mode it reads the
OS username from `/api/auth/me` and shows it in the menubar. Then it runs
`runStartup` (restore last document, or pick one); File → Open opens the same
select-document picker (`documentPicker.ts`
`openDocumentPickerConfirm`) and loads the chosen document. File → Delete and
File → Edit manage whole documents (delete with confirm; title/author) and the
selected chapter's title; Mode, panel widths, and last document persist via
`GET/PUT /api/app/state`. File → Quit asks to save when dirty, then sends the
`quit` IPC channel.

## Layout

- `src/main/main.ts` — sandboxed `BrowserWindow`; removes the default Electron
  menu (`Menu.setApplicationMenu(null)`); Vite URL or `dist/index.html`.
- `src/main/preload.ts` — `window.dockb` (`platform`, `openExternal`, `quit`).
- `src/renderer/` — `index.ts` wires the `ApiClient` and mounts the shell;
  `main.ts` builds it; `api/` is the backend client.
- `vite.config.mts` — Vite/Vitest, :3000, `/api` proxy.
- `tests/` — Vitest (jsdom).
