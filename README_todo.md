# README_todo.md — deferred work

## Executive Summary

`README_todo.md` is the running list of DockB work that is known but not done yet, so nothing
discovered while building is forgotten. Each entry says what is missing, why it matters, and points
at the design document that already settles how it should be built; an entry is deleted when the
work lands, and the design document is expected to absorb it.

Two entries remain. One is small and felt: a signed-in writer has no **Sign out** in the editor's
File menu, so the only way to end your own session is the change-password dialog, and an account
that is signed in on a shared machine stays signed in. The other is the whole MCP server — a second
listener, an endpoint, the tools, and a per-prompt token — which is specified at
`README_mcp_auth.md` and waiting on three decisions before any of it is written.

Everything else this file used to list has landed and been deleted: the admin CLI, password sign-in,
the editor's change-password dialog, and mandatory sign-in with no local mode. Their decisions and
reasoning live in `README_auth.md`, and their mechanics in the package that owns them —
`src/dockb/infrastructure/accounts/README.md` (the user, token and admin-CLI schema),
`src/dockb/infrastructure/session/README.md` (the session cookie), and
`src/dockb/controllers/README_API.md` (the manuscript auth gate and the editor shell it serves).

## Entries

- **Signing out from the editor** — the change-password dialog can sign out, but the File menu
  (`frontend/src/renderer/layout/menubar.ts`) has no **Sign out** item, so a signed-in user cannot
  end their own session without that dialog. `POST /api/auth/logout` exists and works; this is the
  menu entry that calls it. Worth adding: signing out is what someone reaches for on a shared
  machine, and today the route is only reachable from the one screen that is about to disappear.

- **MCP server and its per-prompt token** — `README_mcp_auth.md` §1–§5. Nothing exists yet: no
  second ASGI listener, no MCP endpoint, no tool handlers, no token. The design as decided needs
  no credential store, no admin CLI and no signing key, so the work is the token mint-and-verify
  pair, the public application that mounts only the MCP router, and the tools themselves. §8
  holds three decisions to make first: the measured TTL, whether concurrent prompts are needed,
  and a stable public URL.
