# MCP Authentication and Process Boundaries

## Executive Summary

This document explains how the MCP server authenticates the OpenAI model that
calls it. When Brian's code builds a Responses API request it attaches the MCP
server as a tool and passes a bearer token in that tool's `authorization`
field; OpenAI's infrastructure then calls the MCP server carrying that token.
The token is generated for that one prompt, kept in a live-token map in memory, and expires after
a short, configurable window, so a stolen token is dead within minutes and there is no
credential anywhere on disk.

The MCP server runs **in the same process** as DockB's backend, mounted on its
own listener so the public tunnel cannot reach the manuscript API. That is one
process and two ports rather than two processes, and it is what lets the token
be a plain in-memory value with nothing to provision and no CLI to administer.
Read this for the token design, why there is no authorization server, and why
the two listeners stay separate even though they share a process.

**Status.** This is the decided design, superseding the earlier two-process and
`issued_tokens` draft. The MCP server and its per-prompt token are not yet
implemented; the account and session code that exists today is described in
`README_auth.md`, and the no-local-mode change that prerequisite depended on has
since landed.

## 1. One process, two listeners, two credentials

Two relationships exist, each with a different holder of the credential:

| Relationship | Direction | Credential | Verified by |
| --- | --- | --- | --- |
| Human → DockB editor | browser | Session cookie | DockB backend |
| OpenAI's infrastructure → MCP server | third-party-attested | Per-prompt bearer token | MCP server |

There is no third row. In an earlier draft the MCP server called the backend
with its own service credential; because both now live in one process (§5), it
calls the service methods directly and there is nothing to authenticate.

The model itself never holds a credential. OpenAI's infrastructure holds the
token and attaches it to each MCP request; the model only ever sees the tool
results. That matters for the threat model: the model context is where
exfiltration risk lives, and a long-lived credential should not be in it.

One Python process serves two listeners:

- **Loopback listener** (`127.0.0.1:8000`) — the manuscript API (documents,
  chapters, paragraphs, sentences, history), the user-login routes, and the
  editor shell. Never tunnelled.
- **Public listener** (its own port, later reached by an ngrok tunnel) — the MCP
  endpoint and nothing else. This is the only thing ever exposed.

Both are the same process, so the MCP tool handlers call the same service
methods the HTTP API calls, with no HTTP call between them, and the per-prompt
token is a plain in-memory value shared by the code that mints it and the code
that verifies it.

## 2. Decision: a bearer token, not an authorization server (decided)

The caller is our own code. Building a Responses API request attaches the MCP
server as a tool and puts a bearer token in that tool's `authorization` field;
OpenAI's infrastructure then forwards it as `Authorization: Bearer <token>` on
each MCP request. The token does not have to be an OAuth token — the field
carries API keys and any other scheme the server implements — and nothing in
that path asks DockB to mint anything at request time.

Because no MCP *host* drives the flow, the discovery and registration surface of
OAuth 2.1 is never entered. None of the following is implemented, and none is
reachable:

- No `/.well-known/oauth-protected-resource` (RFC 9728) or
  `/.well-known/oauth-authorization-server` (RFC 8414). These exist so a client
  that got a 401 can discover where to authenticate; our client is handed the
  token up front.
- No `/.well-known` challenge on a 401. A bare `WWW-Authenticate: Bearer` is
  what is left, because there is nothing to point at.
- No `/authorize` endpoint, consent page, authorization codes, `state`, PKCE, or
  redirect URIs.
- No client registry, and so no client id or client secret. There is no client
  in the protocol sense, so there is no client identity to manage.
- No dynamic client registration (RFC 7591), which is the endpoint this would
  otherwise need.
- No refresh token and no token endpoint, because nothing is minted at runtime.

**What would reverse this.** If an MCP *host* — ChatGPT, Codex, Claude Desktop,
Cursor — ever connects to the MCP server directly rather than our code handing
it a token, that host runs the authorization-code + PKCE flow and requires the
discovery metadata above. Note that such a host does **not** support the
client-credentials grant, so the registry, `/authorize`, PKCE and a redirect-URI
allowlist would all become necessary at that point. That is the single trigger
to revisit, and it has not happened.

A spec-complete authorization server would otherwise be a large amount of
unexercisable code: every feature of it exists to solve a problem this flow does
not have.

## 3. Decision: per-prompt secrets held in memory (decided)

There is no credential store. The token for a prompt is minted immediately
before the request that carries it, from a fresh random secret put in a
module-level map of live tokens keyed by expiry, and dropped when its entry
expires. A process restart invalidates every token it held.

Preparing a prompt:

1. Generate a new secret (`secrets.token_bytes`) and put it in the live-token
   map under the expiry set in step 2, pruning any entries whose expiry has
   already passed. The key is the expiry as an integer count of microseconds, so
   the field is dot-free and two mints — which happen one after the other in
   this process — cannot share a key.
2. Set the token's expiry at *now* plus the TTL from `DOCKB_MCP_TOKEN_TTL_SECONDS`
   (default `300`), and stamp the token with this prompt's identity.
3. Put the token in the MCP tool's `authorization` field.

Verifying a request:

1. Parse the expiry and prompt identity. If the expiry has passed, or no live
   entry is keyed by it, reject.
2. Recompute the MAC over both with the secret from that entry.
3. Compare in constant time. A mismatch means the token is not the one minted
   for that expiry.
4. Log the prompt identity, so a token seen out of place traces to one request
   (§4).

The token is `expiry.prompt_id.mac(expiry + "." + prompt_id)`, where `mac` is an
HMAC-SHA256 under the secret in that expiry's live-map entry and `prompt_id` is
an opaque per-prompt handle. Both fields travel in the clear; neither is a
secret, and the MAC covers both so neither can be altered without invalidating
the token. Binding the identity into the MAC rather than merely appending it is
what makes it attributive — a prompt id that could be swapped would let one
request borrow another's attribution.

**A MAC, not a signature.** An earlier draft signed with a private key so a
verifier could check a token with only a public key. That bought offline
verification by a party that holds no secret — which mattered only when the MCP
server was a separate implementation in a separate language. There is no such
party here: the code that mints the token and the code that verifies it are the
same process, so both hold the secret and a shared-key MAC is sufficient and
smaller. No keypair means nothing to generate, store, rotate, or lose.

**What this buys.** There is no long-lived secret anywhere: not in an
environment variable, not in a table, not a key on disk. A secret lifted off the
machine is useless after the current TTL, and a token lifted off the wire is
useless after that TTL. Nothing has to be provisioned by hand, so there is no
admin CLI, no `keygen`, no provisioning step, and no secret to rotate out of
band.

**Concurrency, and one deliberate sharp edge.**

- **Concurrent prompts each get their own entry, pruned by expiry.** Because the
  map is keyed by expiry, two overlapping agent sessions do not invalidate each
  other: each prompt mints its own secret and its own entry, and expired entries
  are pruned as new ones are added. The cost is that the map, not the act of
  preparing the next prompt, is what bounds a token — so the TTL is the only
  time bound left (§4).
- **The TTL must cover model latency, not just tool duration.** The clock starts
  when the prompt is prepared, but the token is not presented until the model
  decides to call a tool — which may be a long way off for a reasoning model —
  and the call then runs to completion. So the bound is *worst-case time to
  first tool call + longest tool call + retries*. Verification happens on
  request entry and not again during streaming, so a call that outruns its TTL
  still completes; what must not expire is the window before the call arrives.
  The default is 300s, set from `DOCKB_MCP_TOKEN_TTL_SECONDS` (§8), and should be
  raised without a code change if the measured bound requires it.

## 4. Decision: what bounds a token now (decided)

The earlier draft scoped tokens, on the reasoning that the MCP server is reached
over a public tunnel and the token is handed to a third party that stores it and
sends it across the internet — so it is the most likely credential to leak.
That reasoning holds. What changes is the mechanism, because a grant has to live
on the token, and the token is a MAC over an expiry and a prompt id with no room
for a scope set that a verifier would have to resolve.

Two bounds replace it, in increasing order of cost:

- **The TTL.** This is the main one, and it is why §3 sets it from
  `DOCKB_MCP_TOKEN_TTL_SECONDS` rather than hard-coding it. A leaked token is a
  leak for the length of that window and no longer, without anyone having to
  notice and act.
- **What one call can return.** Unchanged and still required: a token that can
  read chapters can read *unbounded* chapters, so the MCP tools cap the size of a
  single response. A leaked token with minutes to live should still not be able
  to pull the whole manuscript in one call.

**Attribution.** `last_used_at` and a client `label` no longer exist, because
there is no row to hold them. The replacement is the prompt identity bound into
the token and logged on every MCP call (§3). That is more precise than a
credential label: it identifies *which request* a token belonged to, so a token
seen somewhere it should not be traces to one prompt rather than to "the MCP
client".

## 5. Decision: one process, two listeners (decided, superseding two processes)

The MCP server and the DockB backend are one Python process serving two
listeners: the loopback one carries the manuscript API and the editor shell, and
the public one carries the MCP endpoint and nothing else. Two ASGI applications
in one process, bound to different addresses.

**Why two listeners rather than one app with `/mcp` mounted on it.** The concern
is routing, not processes. The public tunnel must not be able to reach a
manuscript route, and the cheapest guarantee is that the application serving
the public port does not contain one. Mounting the manuscript API and the MCP
endpoint on a single listener puts both within reach of the tunnel, and no amount
of care in the MCP handler changes that.

**Both reasons the earlier draft gave for a separate process are now stale.**
They were correct when written and were overtaken by other work:

- It claimed *"the manuscript API has no authentication"*, citing
  `app_factory.py:38-45`. The content routers do carry the gate:
  `app_factory.py:36-44` attaches `dependencies=_authenticated`
  (`Depends(get_current_user)`) to documents, chapters, paragraphs, sentences,
  history, notifications and imports. Only `auth` and `app_state` are open,
  which is right — `auth` is how a caller obtains a session.
- It claimed the session cookie is set with `path="/"`. It is `path="/api"`
  (`src/dockb/controllers/auth.py:100`), so a path like `/mcp` would never
  receive it. `README_auth.md` §4 had this right.

**The prerequisite has landed.** `README_auth.md` §6 made every user sign in:
`requires_login` is unconditionally true, `DOCKB_LOCAL_MODE` does not exist, and
`get_current_user` refuses an unauthenticated caller instead of falling through to
the OS user. Every content route now needs a session cookie that
`/api/auth/login/password` mints, so the last reason for a separate process is
gone and **the two-listener split is now this work's design, not a workaround for
a bug.**

What remains is the part that has never been built: the public listener itself.
`app_factory.py` mounts one router set on one app, so there is no second listener
to speak MCP on yet. That is the next build step, not this section's blocker.

**What one process costs.** spaCy is CPU-bound and holds the GIL, so a long
MCP-triggered analysis competes with the editor rather than being isolated from
it. The mitigation already exists: analysis runs as a background job
(`README.md`), off the request path, so this is a latency question rather than a
correctness one. The crash domain is also shared — a fault in a tool call, which
runs agent-authored input and is the part most exposed to prompt injection, can
take down the editor as well as the MCP request. That is not a new exposure: the
API already runs document processing on request.

**What one process buys.** The spaCy document cache and the job queue are shared
rather than duplicated, so the MCP server reads the cache the editor warmed
instead of re-analysing over HTTP. And it is what makes §3's design possible at
all: the live-token map is module state instead of something that has to
be carried across a process boundary to a listener that must not itself be
reachable.

**The exposure requirement, restated.** Only the MCP listener is ever tunnelled
or public. The loopback listener is not, and the MCP application must not mount
any manuscript router.

## 6. Decision: the MCP server is Python, because it is the same process (decided)

The earlier draft left this open between Python and TypeScript, because it
determined whether the MCP server could import DockB's packages or had to call
them over HTTP. One process settles it: the tool handlers are ordinary Python in
the same interpreter, so there is nothing to choose and no HTTP between them.

The consequence that mattered most when this was open is the one that has gone
away. A second language would have meant a second implementation of token
validation, free to drift out of step with the first — and a bug in one would be
a bypass of the other's check. Sharing the process shares the verifier, so there
is only one definition of valid.

TypeScript returns only if the MCP server leaves this process, which would also
mean reintroducing the credential of §1's deleted third row.

## 7. Revocation is automatic

There is no revocation command, because there is nothing to revoke. A token stops
verifying when either of two things happens:

- **Its TTL passes.** The entry expires and is pruned from the live-token map.
- **The process restarts.** Nothing is in memory to survive it.

Both are automatic, which is a stronger property than the earlier JWT design
had. That design was stateless, so revoking meant either consulting a store or
letting a short TTL lapse — the earlier draft settled on "a CLI kill-switch plus
a short TTL is sufficient". There is no kill-switch to forget to pull, because
the mechanism *is* the kill-switch.

Concurrent prompts no longer revoke each other (§3), so this is no longer a
blanket "the next prompt kills everything" property. Revoking *one* live token
while leaving the others alone is now possible — drop its entry from the map —
but nothing in the design needs it, so no command exposes it.

## 8. Decision: TTL, concurrency and public URL (decided)

The three questions this revision had open are settled:

1. **The TTL is configurable, defaulting to 300s.** It is read from
   `DOCKB_MCP_TOKEN_TTL_SECONDS` and covers worst-case time to first tool call
   plus the longest tool call plus retries (§3). The default is deliberately
   generous so the window comfortably spans model latency; it can be raised
   without a code change if the measured bound demands it.
2. **Concurrent prompts are supported.** The single in-memory secret is a map of
   live tokens keyed by expiry (§3), so overlapping agent sessions mint
   independent entries that do not invalidate each other, and expired entries are
   pruned as new ones are added.
3. **The public URL comes from an environment variable.**
   `DOCKB_MCP_PUBLIC_URL` holds the full base URL of the MCP listener (scheme and
   host, e.g. `https://mcp.example.com`) — an ngrok reserved domain or real
   hostname rather than a per-restart tunnel URL — and it is what our code passes
   to the LLM when it attaches the MCP server as a tool, so the address in the
   client's configuration does not change under a reconnecting client. The domain
   itself is provisioned outside this codebase.

## 9. Resolved questions

Settled while designing, or by this revision:

- **No authorization server** — the caller is our own code handing OpenAI a
  bearer token, so discovery, registration, `/authorize`, PKCE and refresh tokens
  are unreachable (§2). The trigger that would reverse it is recorded there.
- **No credential store and no admin CLI** — the token is minted per prompt from
  an in-memory secret, so there is no `issued_tokens` table, no client registry,
  no `keygen` and nothing to provision by hand (§3).
- **A MAC, not a signature** — the verifier shares a process with the minter, so
  there is no third party needing a public key, and no keypair to manage (§3).
- **What bounds a token** — the TTL and a cap on what one call returns; scopes
  had nowhere to live on the token (§4).
- **One process, two listeners** — shared state and no HTTP between the tool
  handlers and the services, with the public port unable to reach a manuscript
  route (§5). This supersedes the two-process decision.
- **Python** — settled by being the same process, not chosen between options
  (§6).
- **Revocation is automatic** — TTL and restart, with no command to forget to
  run (§7).
- **TTL, concurrency and public URL** — `DOCKB_MCP_TOKEN_TTL_SECONDS` defaulting
  to 300s, a live-token map so prompts overlap, and `DOCKB_MCP_PUBLIC_URL` for
  the address handed to the LLM (§8).
