# DockB Frontend

## Executive Summary

This is DockB's desktop editor. It is a window that talks only to the server: sign in, open a document, edit a chapter, or import a whole document from a folder on disk. It never writes files itself — an import reads a directory the user picks and hands it to the server, which does the writing. The window does not even load its own interface from disk; the backend serves it, so the app and the API share an origin and the signed-in session reaches every route.

Read it to run the app, to find which file owns the chapter list, the editor, and login, and to see how a folder on disk becomes a document. How the window should look is in `../README_markdown_editor_ui.md`.

## API client and session

The renderer is served **by the backend** at `/editor/`, not loaded from a local file. `src/main/main.ts`
builds that URL from `DOCKB_API_ORIGIN` (default `http://localhost:8000`) and loads it with
`loadURL`; when `VITE_DEV_SERVER_URL` is set it loads that instead, so `npm run dev` is unchanged.
Being same-origin with the API is what lets the `SameSite=Strict` session cookie reach the gated
routes and removes the need for both `credentials: "include"` and any CORS grant. `README_auth.md`
§4 has the reasoning.

The renderer talks to the backend through a typed client in
`src/renderer/api/`: `client.ts` (documents, chapters, chapter-document
lifecycle, reorder, app state, auth), `http.ts` (`ApiError` on non-2xx), and
`session.ts` (`checkSession`, `signInWithPassword`, `changePassword`, `signOut`).
`index.ts` wires the client into
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

### Importing a document directory

`File > Import…` reads a document directory the user picks and sends it to
`POST /api/import`; `layout/importDialog.ts` and `ApiClient.importDocument` own the
steps. Three things worth knowing that the code cannot say for itself:

- The picked directory's own name is **not** in `webkitRelativePath`, and the server
  needs it — it is the shared first segment every part sits under, and it becomes
  the document's title. That is why the renderer reads a path at all.
- A directory whose path cannot be read is reported **before** the confirm dialog,
  so the user is never asked to confirm a form that was never going to send.
- The import does **not** open the imported document. The response carries
  per-chapter ids but no document id, so there is nothing to select; the document
  appears in `Open`, which re-lists each time it is used.

`layout/overlay.ts` owns the modal shape every dialog shares and
`layout/selectList.ts` the choose-then-confirm list the pickers use. A new dialog
should build on `openOverlay` rather than assembling its own.

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
- `menubar.ts` — File (Open, Import…, Save, Delete ▸ Document, Edit ▸ Document/Chapter,
  Quit), Mode, Settings (Language… dialog); dropdowns and nested submenus dismiss on outside click
  or Esc. There is no **Sign out** item: the only route to `POST /api/auth/logout` is the
  change-password dialog's own button. See `../README_todo.md`.
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

`mountShell` asks `GET /api/auth/config`, which always reports `login_required: true`,
so the sign-in gate is always shown; the username comes from `/api/auth/me` and is
shown in the menubar. The gate itself is `layout/signInFlow.ts`'s `ensureSignedIn`,
which resolves the whole question in one place: an existing session if there is one,
otherwise `signInGate.ts`'s username/password form, and then `changePasswordDialog.ts`
if `/api/auth/me` reports a password change is owed. It resolves `null` when the user
cancels or signs out, and `boot` stops there rather than issuing requests that would
all be refused.

The gate is **password-only** — there are no provider buttons (`README_auth.md` §7),
so an account that exists only through OAuth needs `dockb users set-password` before
it can open the editor. The backend's OAuth routes are unchanged and still work by
URL; only this screen stopped offering them.

A first-time user signs in twice. Changing a password stamps the account's credentials
and refuses every session older than the stamp, including the one the change arrived
on, so the flow presents the sign-in gate again rather than continuing on a dead
session. The new password is never held in memory to post a second time — the user
types it. Both dialogs render a refusal inline, above the buttons, and clear the
password field on failure so a wrong guess does not sit in the DOM; the username
survives, because a mistyped password is no reason to retype the name. Then it runs
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
