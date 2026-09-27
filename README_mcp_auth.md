# MCP Authentication and the Two-Process System

## Executive Summary

This document explains how the MCP server and DockB's backend authenticate to
each other, and to the OpenAI model that calls the MCP server. The model calls
the MCP server with a bearer token that is generated ahead of time and handed
to it in the OpenAI Responses API payload; the MCP server in turn calls
DockB's backend with its own service credential. Neither credential is issued
through a login screen, because there is no human-consent step anywhere in the
flow: Brian is the only user and provisions both credentials himself. Both
credentials are asymmetric JWTs — only the token issuer holds the private
signing key, and anything that verifies a token needs only the public key,
which is not a secret.

The two services run as two processes, not one. The MCP server is the part that
faces the internet (through an ngrok tunnel today, a public HTTPS endpoint
later), so it is the only one that is ever exposed; the DockB backend stays on
the loopback interface. The MCP server imports DockB's Python packages and
calls the same service methods the HTTP API calls, so the two services share
code and in-memory state without making HTTP calls between them. Read this for
the token design, the two-process boundary, and why exposing a single combined
process would be unsafe.

**Status.** This is the decided design. The MCP server, the token issuer, and
the explicit-local-mode change are not yet implemented; the account and session
code that exists today is described in `README_auth.md`.

## 1. The two processes and the three credentials

Three relationships exist, in three different directions, each with a different
holder of the credential:

| Relationship | Direction | Credential | Verified by |
| --- | --- | --- | --- |
| Human → DockB editor | browser | Session cookie | DockB backend |
| MCP server → DockB backend | service to service | Service credential (JWT) | DockB backend |
| OpenAI model → MCP server | third-party-attested | Bearer token (JWT) | MCP server |

The first relationship is the user login covered in `README_auth.md`. This
document covers the other two, which are machine-to-machine: the MCP server
authenticates as a service to the DockB backend, and the model authenticates to
the MCP server with a token that was handed to it out of band.

The two processes are:

- **DockB backend** (`uvicorn`, port 8000) — the manuscript API (documents,
  chapters, paragraphs, sentences, history), the user-login routes, and the
  **token issuer** (a Python package living in-process). This is the process
  that mints tokens.
- **MCP server** (its own `uvicorn`, its own port) — exposes the MCP endpoint to
  the model. It verifies the model's bearer token, and calls the DockB backend
  for every manuscript operation.

The MCP server imports DockB's Python packages and calls the same service
methods the HTTP API calls. There is no HTTP call between the MCP server and the
DockB backend (see §5).

## 2. Decision: a token issuer, not an authorization server (decided)

The MCP credentials are issued in the **client-credentials** shape
(RFC 6749 §4.4): machine-to-machine, with no user, no consent screen, no
redirect, and no interactive step. The token is provisioned by Brian (via a CLI)
and handed to the holder out of band. This means the parts of an authorization
server that exist to model a human consenting to a third-party app are never
exercised:

- No `/authorize` endpoint and no consent page.
- No authorization codes, `state`, PKCE, or redirect URIs.
- No refresh tokens (a service credential is re-minted, not refreshed).
- No token-introspection endpoint (see §5 — verification is offline).

The design deliberately does not implement these. A spec-complete authorization
server would be a large amount of unexercisable code to maintain and audit for
no benefit, because every feature of it exists to solve a problem this flow does
not have.

## 3. Decision: `issued_tokens`, not an OAuth client registry (decided)

The issuer keeps a small table of issued credentials. It is deliberately **not**
modelled as a registry of OAuth clients: with a single consumer and out-of-band
provisioning, the client *is* the token, and a `clients` table would invite the
rest of the OAuth spec to be built around it. The table is named `issued_tokens`
to keep the design small.

`issued_tokens` (schema owned by the token-issuer store, following the
`AccountStore` pattern in `src/dockb/infrastructure/accounts/store.py`):

| Column | Purpose |
| --- | --- |
| `token_hash` | Hash of the credential. The plaintext is shown once at mint time and never stored. |
| `label` | Human-readable name, e.g. the model's name. |
| `scopes` | The granted scopes (see §4). |
| `created_at` | When it was minted. |
| `last_used_at` | Last time a verification succeeded. |
| `revoked_at` | Set when revoked; NULL while active. |

Tokens are minted and revoked by an admin CLI, like the account-lifecycle CLI
described in `README_auth.md` §7. There is no HTTP endpoint that mints tokens.

**Asymmetric JWTs from day one.** Tokens are signed with a private key (`RS256`
or `EdDSA`); only the issuer holds it. Verification requires only the **public**
key, which is not a secret and is handed to the DockB backend and the MCP server
as configuration. This matters for two reasons:

- It makes verification an **offline, pure function** of the token and the
  public key. The DockB backend and the MCP server each verify locally — no
  network hop, no introspection call, and no availability coupling to the
  issuer.
- It avoids the "two implementations of token validation drift apart" problem.
  If the DockB backend (Python) and the MCP server (a different language, see
  §6) each implemented symmetric validation, they would drift, and a bug in one
  would be a bypass of the other's check. With a public key there is one
  definition of "valid" — the signature — and it is checked with a well-tested
  library in each language.

Asymmetric signing is chosen from the start because migrating from a symmetric
scheme to an asymmetric one is a breaking change for every verifier.

## 4. Decision: scopes from day one (decided)

Even though there is a single consumer, tokens are **scoped**. A scope is a
short string such as `dockb:read` or `dockb:write`, recorded on the
`issued_tokens` row and checked at verification time.

This is driven by the exposure model, not by multi-client plans. The MCP server
is reached over a public ngrok tunnel, and the model's bearer token is handed to
a third party (OpenAI) that stores it and sends it across the internet. That
token is the most likely credential to leak. With scopes, a leaked token is a
**read-only** leak rather than a read-write one. This is the cheapest security
win available and there is no reason to defer it.

Two related bounds go with it:

- **Bound what a single MCP call returns.** A token that can read chapters can
  read *unbounded* chapters. The MCP tools cap the size of a single response so
  a leaked read token cannot pull the whole manuscript in one call.
- **Log the token's identity on every MCP call.** The `last_used_at` and `label`
  on the `issued_tokens` row are what make a leak visible after the fact.

## 5. Decision: two processes, with the MCP server importing DockB's packages (decided)

The MCP server and the DockB backend are two processes. The MCP server imports
DockB's Python packages and calls the same service methods the HTTP API calls;
there is no HTTP call between the two services. This gives the benefits of a
shared codebase (one verifier, shared in-memory state) while keeping the two
services isolated in the ways that matter.

**Why not one process.** The MCP server is the only component that is exposed to
the network. Today it is reached through an ngrok tunnel; later it will have a
public HTTPS endpoint. The DockB backend should stay on the loopback interface.
Two processes with two ports means the tunnel points at the MCP server's port
only.

A single combined process, with the MCP mounted at a path such as `/mcp`, would
be unsafe, for two reasons that are both live today:

- **The manuscript API has no authentication.** The routers registered in
  `src/dockb/app_factory.py:38-45` have no router-level or app-level auth
  dependency, and only `app_state` (`src/dockb/controllers/app_state.py:43`) is
  behind `get_current_user`. A single tunnel on a combined process would expose
  every document, chapter, paragraph, sentence, history, and notification route
  to the internet. This is a work item in its own right, sequenced before any
  exposure rather than as part of it — see `README_todo.md`.
- **The session cookie is not path-scoped.** It is set with `path="/"`
  (`src/dockb/controllers/auth.py:97`), so it is sent to every path on the host.
  An MCP endpoint on the same host would sit inside the same session cookie's
  scope.

**What the separate process buys**, beyond the narrow tunnel:

- **A separate GIL.** The DockB backend runs spaCy, which is CPU-bound and holds
  the GIL (see `README.md` on the analysis jobs). In one process, a long
  MCP-triggered analysis would degrade the editor's responsiveness directly. In
  two, the editor stays smooth.
- **A separate crash domain.** A fault in a tool call — which runs
  agent-authored input, and is the part of the system most exposed to prompt
  injection — cannot take down the editor or the manuscript.
- **Independent limits.** The MCP server can be capped, rate-limited, and scaled
  independently of the backend.

**The ngrok exposure requirement.** The MCP server's port is the only port that
is ever exposed publicly. The DockB backend is not tunnelled and is not publicly
reachable. Before the MCP server is exposed, the manuscript API on the DockB
backend must be authenticated (it currently is not), and the session cookie
should be reviewed for scope.

## 6. Open question: the MCP server's language

The MCP server can be written in Python or TypeScript. The choice is not a
detail, because it determines how the two services communicate:

- **Python** — the MCP server imports DockB's packages directly. It shares the
  verifier, the `issued_tokens` store, and in-memory state (the spaCy document
  cache, the job queue). No HTTP between the services. This is the layout
  described in §5, and it requires the MCP server to be Python.
- **TypeScript** — the MCP server calls the DockB backend over HTTP and verifies
  tokens with the same public key, using a JWT library for TypeScript. This
  still works because the public key is not a secret (§3), but the two services
  no longer share code and the manuscript calls go over HTTP.

The recommendation is **Python**, given that the only MCP client is a model Brian
calls directly (no third-party MCP clients, so the main argument for TypeScript —
the more mature MCP SDK ecosystem — buys less than sharing the verifier does). If
the TypeScript SDK turns out to lack a needed feature, this is the moment to
revisit.

## 7. Revocation

Revocation is done by the admin CLI, which sets `revoked_at` on the
`issued_tokens` row. How revocation takes effect depends on the token type,
because JWTs are stateless:

- **Service credential (MCP → DockB backend)** — short expiry (minutes) and
  re-mint. The backend checks the issuer (or a cached copy of the
  `issued_tokens` store); a revoked credential stops working when its short TTL
  lapses. There is no long-lived service credential to block.
- **The model's bearer token (model → MCP server)** — this one is
  hand-distributed into a third party and is the credential most likely to leak,
  so it needs to be revocable promptly. The MCP server is its only verifier, so
  it checks it against a blocklist kept from the issuer (or the `issued_tokens`
  store directly, if the MCP server shares it). A CLI kill-switch plus a short
  TTL is sufficient.

## 8. Open questions

1. **MCP server language** — Python or TypeScript (see §6). Determines whether
   the two services share code or communicate over HTTP.

## 9. Resolved questions

Settled while designing:

- **Table naming** — the credential store is `issued_tokens`, not an OAuth client
  registry (§3), so the design does not drift toward a full authorization server.
- **Asymmetric from day one** — tokens are signed with a private key and verified
  with a public key (§3), so verification is offline and the scheme does not need
  a breaking migration later.
- **Scopes on a single-consumer system** — tokens are scoped because the model's
  token is the likely leak, not because there are many clients (§4).
- **Two processes** — the MCP server and the DockB backend are separate processes
  sharing a repository, with the MCP server importing DockB's packages (§5).
- **What is exposed** — only the MCP server's port is tunnelled or public; the
  DockB backend is not (§5).
