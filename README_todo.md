# README_todo.md — deferred work

## Executive Summary

`README_todo.md` is the running list of DockB work that is known but not done yet, so nothing
discovered while building is forgotten. Each entry says what is missing, why it matters, and
points at the design document that already settles how it should be built; an entry is deleted
when the work lands, and the design document is expected to absorb it.

It currently holds two entries. The last one the editor had — no way to send a document
directory to the import endpoint — is done: the editor imports a chosen directory from
`File > Import…` and shows the per-chapter summaries the endpoint returns.

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

- **Admin CLI for accounts** — `README_auth.md` §7. Accounts and password resets are admin-CLI
  only by decision, but `src/dockb/cli/` holds only `import_document.py` and
  `reconstruct_chapter.py`, so there is no `dockb users create`. Until it lands, a fresh install
  has no account and therefore nobody can sign in: the password routes exist (§4) but no
  password does.
- **Password sign-in in the editor** — `README_auth.md` §7. `POST /api/auth/login/password`,
  `/api/auth/change-password` and `/api/auth/logout` exist and are gated, but the editor still
  renders the provider-only gate, so there is nothing on screen to post them from.
- **Every user signs in** — `README_auth.md` §6. Done: `requires_login` is unconditionally true,
  there is no `DOCKB_LOCAL_MODE`, and the OS-user fall-through is gone.
  Land this before any MCP listener work.

- **MCP server and its per-prompt token** — `README_mcp_auth.md` §1–§5. Nothing exists yet: no
  second ASGI listener, no MCP endpoint, no tool handlers, no token. The design as decided needs
  no credential store, no admin CLI and no signing key, so the work is the token mint-and-verify
  pair, the public application that mounts only the MCP router, and the tools themselves. §8
  holds three decisions to make first: the measured TTL, whether concurrent prompts are needed,
  and a stable public URL.
