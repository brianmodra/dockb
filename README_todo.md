# README_todo.md — deferred work

## Executive Summary

`README_todo.md` is the running list of DockB work that is known but not done
yet, so nothing discovered while building is forgotten. Each surviving entry
says what is missing and points at the design document that already settles how
it should be built; entries are deleted as the work lands, and the design
document is expected to absorb them.

One entry remains: the MCP server's tools and the prompt-building that mints a
per-prompt token for each prompt. Everything else this file used to list — the
admin CLI, password sign-in, mandatory sign-in with no local mode, the editor's
change-password dialog and **Sign out** — has landed; their reasoning lives in
`README_auth.md` and their mechanics in
`src/dockb/infrastructure/accounts/README.md`,
`src/dockb/infrastructure/session/README.md`,
`src/dockb/controllers/README_API.md` and `frontend/README.md`.

## Entries

- **MCP tools and prompt-building** — `README_mcp_auth.md` §1–§8. The token mint-and-verify
  pair (`src/dockb/infrastructure/mcp/`), the bearer-gated public listener and its two-listener
  runner (`src/dockb/mcp_server.py`, `src/main.py`) are built; the MCP server still exposes an
  empty `tools/list`. What remains is the tool handlers themselves and the prompt-building that
  mints a token per prompt and hands the caller `DOCKB_MCP_PUBLIC_URL`. The design as decided
  needs no credential store, no admin CLI and no signing key, so the remaining work is the tools
  over the already-wired services.
