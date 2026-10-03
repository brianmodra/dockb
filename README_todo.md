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

- **Explicit local mode** — `README_auth.md` §6. `DOCKB_LOCAL_MODE` is unimplemented, so local
  mode is still inferred from the absence of provider credentials, and `get_current_user`
  serves an unauthenticated caller as the OS user. This is a **blocker, not just a cleanup**:
  until it lands, every gated route on the loopback listener answers anyone who can reach the
  port, which is the last reason `README_mcp_auth.md` §5 keeps the public listener separate.
  Land this before any MCP listener work.

- **MCP server and its per-prompt token** — `README_mcp_auth.md` §1–§5. Nothing exists yet: no
  second ASGI listener, no MCP endpoint, no tool handlers, no token. The design as decided needs
  no credential store, no admin CLI and no signing key, so the work is the token mint-and-verify
  pair, the public application that mounts only the MCP router, and the tools themselves. §8
  holds three decisions to make first: the measured TTL, whether concurrent prompts are needed,
  and a stable public URL.
