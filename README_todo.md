# README_todo.md — deferred work

## Executive Summary

`README_todo.md` is the running list of DockB work that is known but not done yet, so nothing
discovered while building is forgotten. Each entry says what is missing, why it matters, and points
at the design document that already settles how it should be built; an entry is deleted when the
work lands, and the design document is expected to absorb it.

One entry remains: the MCP server's *tools and prompt-building* — the tool handlers and the
per-prompt token minted for each prompt — specified at `README_mcp_auth.md`. The token's
mint-and-verify pair, the bearer-gated public listener and its two-listener runner are now
built, so the remaining work is the tools themselves and the code that mints a token for each
prompt. Everything else this file
used to list has landed and been deleted: the admin CLI, password sign-in, the editor's
change-password dialog, mandatory sign-in with no local mode, and **Sign out** in the File menu.
Their reasoning lives in `README_auth.md`, and their mechanics in the place that owns them:
`src/dockb/infrastructure/accounts/README.md`, `src/dockb/infrastructure/session/README.md`,
`src/dockb/controllers/README_API.md`, and `frontend/README.md` for the editor's gate, sign-out
loop and menu.

## Entries

- **MCP tools and prompt-building** — `README_mcp_auth.md` §1–§8. The token mint-and-verify
  pair (`src/dockb/infrastructure/mcp/`), the bearer-gated public listener and its two-listener
  runner (`src/dockb/mcp_server.py`, `src/main.py`) are built; the MCP server still exposes an
  empty `tools/list`. What remains is the tool handlers themselves and the prompt-building that
  mints a token per prompt and hands the caller `DOCKB_MCP_PUBLIC_URL`. The design as decided
  needs no credential store, no admin CLI and no signing key, so the remaining work is the tools
  over the already-wired services.
