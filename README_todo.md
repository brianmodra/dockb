# README_todo.md — deferred work

## Executive Summary

`README_todo.md` is the running list of DockB work that is known but not done yet, so nothing
discovered while building is forgotten. Each entry says what is missing, why it matters, and
points at the design document that already settles how it should be built; an entry is deleted
when the work lands, and the design document is expected to absorb it.

It currently holds no entries. The last one — the editor had no way to send a document directory
to the import endpoint — is done: the editor imports a chosen directory from `File > Import…` and
shows the per-chapter summaries the endpoint returns.

The auth work in particular is specified at the root (`README_auth.md`, `README_mcp_auth.md`)
rather than in the packages that will own it, because the decisions had to be made before the
code had a home. As that work is implemented, `README_auth.md` should get **smaller**, not
bigger: the decisions and their rationale stay, and the implementation detail moves down into
the package that owns it — `src/dockb/infrastructure/accounts/README.md` (the user, token, and
admin-CLI schema), `src/dockb/infrastructure/session/README.md` (the session cookie), and
`src/dockb/controllers/README_API.md` (the manuscript auth gate and the editor shell it
serves). This mirrors the project convention that the relevant `README*.md` files for a piece
of code are those in its own directory and every parent up to the root.

## Entries

_None. Every known item has been implemented; add an entry here when a gap is found._
