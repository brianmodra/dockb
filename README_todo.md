# README_todo.md — deferred work

## Executive Summary

`README_todo.md` is the running list of DockB work that is known but not done yet, so nothing
discovered while building is forgotten. Each entry says what is missing, why it matters, and points
at the design document that already settles how it should be built; an entry is deleted when the
work lands, and the design document is expected to absorb it.

One entry remains: the whole MCP server — a second listener, an endpoint, the tools, and a
per-prompt token — specified at `README_mcp_auth.md`, with all three design decisions now settled
(§8) so nothing blocks the build. Everything else this file used to list has landed and been
deleted: the admin CLI, password sign-in, the editor's change-password dialog, mandatory sign-in
with no local mode, and **Sign out** in the File menu. Their reasoning lives in `README_auth.md`,
and their mechanics in the
place that owns them: `src/dockb/infrastructure/accounts/README.md`,
`src/dockb/infrastructure/session/README.md`, `src/dockb/controllers/README_API.md`, and
`frontend/README.md` for the editor's gate, sign-out loop and menu.

## Entries

- **MCP server and its per-prompt token** — `README_mcp_auth.md` §1–§8. Nothing exists yet: no
  second ASGI listener, no MCP endpoint, no tool handlers, no token. The design as decided needs
  no credential store, no admin CLI and no signing key, so the work is the token mint-and-verify
  pair over a live-token map, the public application that mounts only the MCP router, and the
  tools themselves. The three decisions §8 used to hold are settled: TTL from
  `DOCKB_MCP_TOKEN_TTL_SECONDS` (default 300s), concurrent prompts via the map, and
  `DOCKB_MCP_PUBLIC_URL` for the address handed to the LLM.
