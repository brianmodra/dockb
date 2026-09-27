# README_todo.md — deferred work

## Executive Summary

`README_todo.md` is the running list of DockB work that is known but not done yet, so nothing
discovered while developing is forgotten. Each entry names what is missing and points at the
design document for it; delete an entry when it is finished.

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

- **The manuscript API has no authentication** — the routers registered in
  `src/dockb/app_factory.py:38-45` carry no router-level or app-level auth dependency, and only
  `app_state` (`src/dockb/controllers/app_state.py:43`) sits behind `get_current_user`. The
  document, chapter, paragraph, sentence, history, and notification routes are reachable by anyone
  who can open port 8000. This is currently safe only because the backend is bound to loopback and
  nothing tunnels it, so it is the first thing to fix after the rest of the auth work and before
  any public exposure. With the MCP server importing DockB's packages in-process rather than over
  HTTP, these routes serve the editor and need session-cookie identity, not a service credential.
  Design: `README_auth.md`, `README_mcp_auth.md`.
  - **Scope** — the six routers carrying no auth: `documents`, `chapters`, `paragraphs`, `sentences`,
    `history`, `notifications` (`src/dockb/controllers/*.py`). `auth` and `app_state` are already
    handled; `desugar.py` is a helper module, not a router, so it is out of scope.
  - **Done when** — every route on those six routers returns 401 without a valid session cookie, and
    the session cookie is no longer scoped to `path="/"` (it is set that way at
    `src/dockb/controllers/auth.py:97`, so it reaches every route including ones meant to be
    private). Whether the gate is added per-route or once as a router-level `dependencies=[...]` is
    an implementation choice; either satisfies the condition.
  - **Documentation home** — when this lands, the gate is described in
    `src/dockb/controllers/README_API.md` and the cookie scope in
    `src/dockb/infrastructure/session/README.md`, not here.
- **Import endpoint and composition wiring** — the directory walker
  (`services/markdown_import.py`) is driven today only by the command line
  (`python -m dockb.cli.import_document`); nothing in `controllers/` exposes it over HTTP and
  `composition.py` does not register it. Design: `infrastructure/changes/README.md`.
- **Friendly CLI errors** — `python -m dockb.cli.import_document` surfaces a raw `KeyError`
  traceback when `NEO4J_URL`/`NEO4J_USER`/`NEO4J_PASSWORD` are missing or unset. Print a
  one-line explanation instead.
- **Filesystem-unsafe titles pass the API** — a document or chapter title containing `/`, `\`,
  control characters, `.`/`..`, or the empty string satisfies the API schema (`title_not_blank`)
  but is rejected by `DocumentStore._validate_title`, so saving/opening it fails with a 500. The
  filesystem-safety rules should be enforced in the schema layer (→ 400) instead of only at file
  access. Design: `infrastructure/document_store/README.md`.