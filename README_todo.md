# README_todo.md — deferred work

## Executive Summary

`README_todo.md` is the running list of DockB work that is known but not done yet, so nothing
discovered while developing is forgotten. Each entry names what is missing and points at the
design document for it; delete an entry when it is finished.

A completed entry was removed here: the two shell commands used to raise a raw traceback when
`NEO4J_URL`/`NEO4J_USER`/`NEO4J_PASSWORD` were missing or empty, and now print one `error:` line
and exit 1. A missing `en_core_web_sm` model is reported the same way. That behaviour lives in
`src/dockb/cli/README.md`.

Two more were removed: the manuscript API now sits behind the session gate, and a document or
chapter title that could escape the document directory is refused by the schema rather than
failing at file access. Both live where they belong — the gate in
`src/dockb/controllers/README_API.md` and the cookie scope in
`src/dockb/infrastructure/session/README.md`; the title rule in
`src/dockb/infrastructure/document_store/README.md`.

The auth work in particular is specified at the root (`README_auth.md`, `README_mcp_auth.md`)
rather than in the packages that will own it, because the decisions had to be made before the
code had a home. As that work is implemented, `README_auth.md` should get **smaller**, not
bigger: the decisions and their rationale stay, and the implementation detail moves down into the
package that owns it — `src/dockb/infrastructure/accounts/README.md` (new, for the user, token, and
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
- **Import endpoint and composition wiring** — the directory walker
  (`services/markdown_import.py`) is driven today only by the command line
  (`python -m dockb.cli.import_document`); nothing in `controllers/` exposes it over HTTP and
  `composition.py` does not register it. Design: `infrastructure/changes/README.md`.
