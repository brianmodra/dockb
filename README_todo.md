# README_todo.md — deferred work

## Executive Summary

`README_todo.md` is the running list of DockB work that is known but not done yet, so nothing
discovered while building is forgotten. Each entry says what is missing, why it matters, and
points at the design document that already settles how it should be built; an entry is deleted
when the work lands, and the design document is expected to absorb it.

It currently holds two entries, and both are about the editor rather than the server: the
renderer cannot yet send the session cookie, and it has no way to send a document directory to
the import endpoint. The backend for both is in place — the manuscript API is gated, and
`POST /api/import` imports an uploaded document directory — so what is left on each is a
frontend path, not a design question.

The auth work in particular is specified at the root (`README_auth.md`, `README_mcp_auth.md`)
rather than in the packages that will own it, because the decisions had to be made before the
code had a home. As that work is implemented, `README_auth.md` should get **smaller**, not
bigger: the decisions and their rationale stay, and the implementation detail moves down into
the package that owns it — `src/dockb/infrastructure/accounts/README.md` (new, for the user, token, and
admin-CLI schema), `src/dockb/infrastructure/session/README.md` (the session cookie), and
`src/dockb/controllers/README_API.md` (the manuscript auth gate). This mirrors the project
convention that the relevant `README*.md` files for a piece of code are those in its own directory
and every parent up to the root.

## Entries

- **The editor cannot send the session cookie, so OAuth mode is unreachable from it** — the
  manuscript API is now gated, and the editor satisfies that gate only in local mode, where
  `get_current_user` falls through to the OS identity. Two independent blockers stand in the way
  in OAuth mode, and neither is fixed by the backend:
  - `frontend/src/renderer/api/http.ts:27` calls `fetch` without `credentials: "include"`. The
    renderer is a cross-origin client — a `null` origin from `file://`, or `localhost:3000` in dev —
    so the browser withholds the cookie on every manuscript request and all of them 401.
  - `SameSite=lax` (`src/dockb/controllers/auth.py`) is not sufficient on its own. A `lax` cookie is
    not sent on a cross-site request, and `file://` → `http://localhost:8000` is cross-site, so the
    cookie stays withheld even once credentials are requested. A cross-site cookie needs
    `SameSite=None` (which in turn requires `Secure`, and so a real origin rather than `file://`).
  - This is the same `null`-origin exposure `README_auth.md` §7 already flags for the future
    password path, seen from the editor's side. Fixing the frontend will not change the
    loopback-only local mode story, and the password work will not fix it either — the renderer has
    to be able to send a cookie at all.
  - **Done when** — with a provider configured, signing in through the editor leaves the manuscript
    API reachable, and the cookie is not sent to any path the API does not serve.
- **The editor has no way to send a document directory** — `POST /api/import` now imports a
  document directory sent as a multipart upload, but nothing in the editor calls it:
  - `frontend/src/renderer/api/http.ts:29` sets `headers: { "Content-Type": "application/json", ... }`
    unconditionally, so a `FormData` body would be sent labelled as JSON and be rejected — the
    browser has to set the multipart boundary itself. The upload needs a call path that omits the
    header when the body is not JSON.
  - There is also no picker: the editor cannot choose a folder on disk and enumerate it into
    the part list the endpoint expects. The browser's directory-picker APIs are Electron-specific
    and still need deciding between them.
  - This is independent of the cookie blocker above: fixing the credentials does not give the
    renderer a way to send multipart data.
  - **Done when** — with a provider configured and the cookie blockers above fixed, the editor can
    import a chosen document directory and show the per-chapter summaries the endpoint returns.
    Design: `src/dockb/controllers/README_API.md` § Import.
