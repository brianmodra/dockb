# Authentication and Accounts

## Executive Summary

This document explains how DockB users sign in and where their accounts live.
Users have their own accounts, created by an admin CLI that issues a temporary
password which the user must change on first sign-in; they can also authenticate
with Google or GitHub. In both cases the backend (not the editor) mints its own
session cookie, and stores accounts, tokens, and per-user app state in a small
SQLite database. Provider tokens never reach the editor. **There is no local mode:**
every request requires a sign-in, and `get_current_user` falls through to the OS user
when no provider is configured (see §6).

The routes, session gate, and app-state endpoints are implemented. On first run
the editor shows a Sign-in button, then restores the last document or asks the
user to pick one. Read this for the login flow, storage, and security choices.

**Part of this document is a specification, not a description.** §6 and §7 record decisions that
have *not* been implemented; the code still behaves as this document previously described. The
table below is the baseline, verified against the code, so a build can start from it.

| Decision | The code today | The target | Done when |
| --- | --- | --- | --- |
| §6 every user signs in | `requires_login` is `bool(self._providers)` (`services/auth_service.py`), so with no provider configured `get_current_user` falls through to the OS user and the gated routes are open to any caller today. `DOCKB_LOCAL_MODE` exists nowhere in `src/`. | `requires_login` is unconditionally true. No `DOCKB_LOCAL_MODE`, no OS-user fall-through, and `local_username`/`ensure_local_user`/`get_or_create_local_user` are removed. `DOCKB_SECRET_KEY` becomes required rather than optionally replaced by an ephemeral key. | With no provider configured and no session cookie, a gated route answers 401 instead of serving the request. No deployment setting can make it serve an unauthenticated caller. |
| §7 account lifecycle is admin-CLI only | No admin CLI exists: `src/dockb/cli/` holds only `import_document.py` and `reconstruct_chapter.py`. There is no password column on `users`. | A CLI that creates accounts and sets or resets a password. No HTTP registration or recovery route. | An account can be created with a password and then sign in. No route accepts a registration or reset request. |
| §7 password login (in build) | Not implemented. No password-hashing library is installed — `pyproject.toml` has `cryptography` and stdlib `hashlib` only. | Argon2id, verified off the event loop, constant-time on the not-found path, rate limited. | A wrong password and an unknown username cost the same and both fail; a correct password mints a session cookie. |
| §7 username normalization, `email` uniqueness, soft delete | `username` is `UNIQUE` but unnormalized, so SQLite's case-sensitive comparison admits `Brian` and `brian` as two accounts. `email` carries no constraint. `get_or_create_local_user` inserts an *empty string* email, which would collide under a unique constraint. No `deleted_at`. | Usernames lowercased and stripped; `email` nullable but `UNIQUE`, with every passwordless row storing `NULL` rather than `''`; `deleted_at` for a soft delete that keeps `app_state` and OAuth links. | The CLI cannot create two accounts differing only by case, a local-mode and a federated row coexist, and a deleted account keeps its manuscripts attributable. |
| `/api/auth/config` response | Returns `{"login_required", "providers"}` (`controllers/auth.py`); the editor branches on `login_required` at `frontend/src/renderer/main.ts`. | `login_required` becomes constant `true`, and the editor renders a username/password form whenever it is true, with provider buttons below it when `providers` is non-empty. No new field: password login is always available, so there is no state left for a flag to distinguish. | With no provider configured the editor still shows a usable password form rather than an empty gate, and with providers configured it shows both ways in. |

As this work lands, this document should get smaller. The decisions and their rationale stay here;
the implementation detail moves down into the package that owns it — `infrastructure/accounts/`
(the user and token schema and the admin CLI), `infrastructure/session/`, and
`controllers/README_API.md`. See `README_todo.md`.

## 1. Context and constraints

- The backend owns the knowledge graph (Neo4j), the markdown file tree, and git. Accounts and
  sessions are none of those: they are simple, transactional rows, so they get a **relational**
  database rather than the graph.
- The editor is a thin client. It never sees services, repositories, the filesystem, or — by this
  design — the provider's tokens. It authenticates to the backend and that is all.
- Mobile (iOS/Android) is a real future requirement, so an account model must exist now rather than
  being bolted on later; the flow below does not presume a browser shell and works for any client.
- OAuth login is implemented. The backend's own session is a **signed HttpOnly cookie**
  (`dockb_session`, issued by `SessionSigner`); the in-memory `SessionManager`
  (`src/dockb/infrastructure/session/session_manager.py`) keeps a live `SessionContext` per
  account while the process runs, so a backend restart invalidates login — the user signs in again.
  The earlier `TokenValidator` scaffolding is superseded by the signed cookie.

## 2. Decision: backend is the confidential OAuth client (decided)

The OAuth flow is **Authorization Code + PKCE** (RFC 8252, "OAuth 2.0 for Native Apps"):

1. The editor opens the system browser to the provider's consent page. It never handles the code.
2. The provider redirects to `http://localhost:<port>/callback` served by **FastAPI**.
3. The backend exchanges the code for tokens using the provider client secret, saves the refresh
   token (encrypted), resolves the account, and mints **its own session** (HttpOnly cookie) that the
   editor presents on every subsequent API call.
4. On each request the controllers receive the session context for that account and serve that
   user; they do not re-contact the provider.

The alternative — the editor holding a public-client token — loses: refresh tokens would sit in
the editor's storage (a worse thin client), and the backend could not control session expiry.
Rejected for exactly that reason.

Consequences:

- The provider's access/refresh tokens exist only inside the backend.
- FastAPI needs the loopback callback path; the editor only needs to open a URL.
- `SessionManager` keeps per-account `SessionContext`s in memory (as today), so token validation
  happens at login, not per request.

## 3. Decision: accounts and state live in SQLite (decided)

The relational store is **SQLite via the Python standard library `sqlite3`** (no ORM), its file
`dockb_app.db` **beside the backend's owned directory** — the chapters directory the composed
`AuthService` receives as its `base_dir`. The chapters directory is `DOCKB_CHAPTERS_DIR`, defaulting
to `cwd`/`dockb_chapters_dir` when unset, and is created (and git-initialized) when missing
(`resolve_document_base_dir` in `composition.py`). This keeps all server-owned on-disk state in one
place, with zero-ops on a single machine. Foreign keys are enforced (`PRAGMA foreign_keys=ON`), so
deleting a user cascades to its OAuth links and app state.

Three tables (`src/dockb/infrastructure/accounts/store.py` owns the exact schema):
`users`, `oauth_accounts` (per provider account, holding the encrypted refresh `token` and its
`expires_at`), and `app_state` (per user, holding the editor state the UI record keeps open).
User identity is the unique `users.username` column everywhere: sessions, cookies, and app state
carry the username — the account's own for a password login, the OAuth profile username otherwise.
`users` keeps an internal UUID `id` only for the `oauth_accounts` foreign key; `app_state` and the
public store accessors are keyed by `username`.

The refresh-token `token` column is encrypted with Fernet under a key derived from the server
secret (`DOCKB_SECRET_KEY`), so the store doubles as a credential store and is treated as one.
Moving to Postgres later means re-implementing the small `AccountStore` against a new driver; the
store interface and route-controller call sites do not change.

## 4. Security properties (decided)

- **OAuth `state` and PKCE.** The authorization request carries both; the callback verifies them,
  so logins cannot be CSRF'd or the code swapped.
- **Refresh tokens encrypted at rest.** The `token` column is encrypted with a key derived from a
  server secret (e.g. `cryptography` Fernet) — never plaintext. This is a credential store and is
  treated as one.
- **Episode secrets, not repo secrets.** Provider client id/secret come from environment
  variables/`.env` only, never committed.
- **HttpOnly session cookie.** The backend's own session is not readable by JS; the editor holds no
  provider credential that could leak. It is scoped to `/api`, so it is sent to the manuscript
  routes that authenticate it and to nothing else the server serves, including `/editor` and
  `/callback`.
- **Same-origin editor.** The renderer is served by the backend rather than loaded from `file://`,
  so no cross-site cookie is needed and no CORS grant is issued. This is what keeps the `null`
  origin — which every `file://` page sends — from reading the API.
- **Loopback callback scoped.** The OAuth client for the desktop app registers only the loopback
  redirect URI, so the code cannot be intercepted by a third origin.

## 5. Providers (decided initially)

Google and GitHub, configured by environment variables:

- `OAUTH_GOOGLE_CLIENT_ID`, `OAUTH_GOOGLE_CLIENT_SECRET`
- `OAUTH_GITHUB_CLIENT_ID`, `OAUTH_GITHUB_CLIENT_SECRET`
- `OAUTH_CALLBACK_PORT` (the loopback port for the login redirect)
- `DOCKB_SECRET_KEY` (server secret; derives the Fernet key that encrypts refresh tokens, the
  session-cookie signer key, and the password pepper). **Required** — there is no ephemeral
  fallback (see §6).
- `OAUTH_SESSION_TTL_HOURS` (session cookie lifetime, default 48)

Configuring a provider is adding its env pair; the flow code is provider-agnostic apart from the
consent URL and the token exchange profile.

## 6. Decision: there is no local mode — every user signs in (decided)

**Every user authenticates with a username and password. There is no mode in which a
request is served without a login.** `DOCKB_LOCAL_MODE` does not exist and local mode is
gone, not deferred.

This reverses the previous decision, which made local mode opt-in via
`DOCKB_LOCAL_MODE=true`. The reason for dropping it is that opting in was the wrong shape
of control. A local-mode flag is an authentication bypass that ships *enabled or disabled
by an environment variable*, so its safety depends on an operator knowing it exists, and
the failure is silent: a deployment that sets it serves every request as the OS user with
no error anywhere. Nothing in the product needs that bypass — the accounts, the
lifecycle and the password flow all work for one user or fifty — so the mode was removed
rather than made safe. Requiring a login unconditionally is the version with no
misconfiguration that opens it.

The consequences, all deliberate:

- `requires_login` is always true. The `/api/auth/config` contract keeps the field, because
  the editor branches on it, but it is no longer a variable the deployment sets.
- `AuthService.local_username`, `AuthService.ensure_local_user` and
  `AccountStore.get_or_create_local_user` are removed. They existed only to serve the OS
  user without a login, and keeping them would leave code implying a path that is not
  supported.
- `get_current_user` has no fall-through. There is no branch in which a missing cookie
  resolves to an identity.
- `DOCKB_SECRET_KEY` is **required**, with no ephemeral fallback. This follows from the
  removal rather than being decided alongside it: with no local mode, the secret signs
  session cookies, encrypts refresh tokens *and* peppers password hashes, so a key
  generated per process would invalidate sessions, tokens and every password on every
  restart. `wire()` substitutes an ephemeral key today; that substitution is removed.
- **Nobody can sign in until an account exists**, so the first account comes from the CLI,
  under the same admin-only rule as every other account (§7). A fresh install therefore
  presents a sign-in that no one can pass until an administrator runs `dockb users create`
  on the host. This is the accepted cost of not having a bypass.
- The built Electron shell loads the renderer from the **backend**, at `/editor/`, so the
  editor is same-origin with `/api`. That is what lets the `SameSite=lax` session cookie
  reach the gated routes: a `file://` renderer talking to `http://localhost:8000` is a
  cross-site request, and browsers withhold a `lax` cookie on those. It also means the
  app needs **no CORS middleware**, which is the stronger half of the win — a grant for
  the `null` origin a `file://` page sends, with credentials, let any local file read the
  API as the signed-in user. The Vite dev server needs none either, because its `/api`
  proxy is same-origin to the browser. See
  `src/dockb/controllers/README_API.md` § The editor shell and `editor_shell.py`.

This also removes the precondition on `README_mcp_auth.md`: its public listener needed
login to be unconditionally required before it opened, and that is now true of the
baseline rather than of pending work.


## 7. Decision: account lifecycle is admin-CLI only (decided)

Accounts are created, and passwords reset, by an admin-only command-line tool. There is no
self-registration and no recovery flow over HTTP. That removes, as a class:

- No `POST /api/auth/register` endpoint, and so no registration policy to decide or enforce.
- No email verification step.
- No password-reset token flow, no expiry on such a token, and no email delivery.
- No account-takeover surface reachable from a recovery path.

This is a deliberate fit for the current stage: DockB is a writing tool with a small, known set of
users, and a CLI is the right weight for administering it. Opening DockB to untrusted users would
require a hosted registration and recovery flow, and this decision would be revisited then.

### The admin CLI

| Command | Effect |
| --- | --- |
| `dockb users create --username <name> --email <address>` | Generates a temporary password, prints it once, sets `must_change_password`. |
| `dockb users list` | Every account with its state, including soft-deleted ones. Never prints a password or a hash. |
| `dockb users block <username>` | Refuses logins and ends live sessions, on the next request. Reversible. |
| `dockb users unblock <username>` | Reverses the above. |
| `dockb users delete <username> --yes` | Soft delete: sets `deleted_at`, refuses logins, ends sessions. |
| `dockb users undelete <username>` | Clears `deleted_at`. Restores the account without touching its credentials. |
| `dockb users set-password <username>` | Re-issues a temporary password and re-arms `must_change_password`. |

None of these reach into a running server. `block`, `delete` and `set-password` end a live session by
stamping `credentials_changed_at`, which the server compares on its next request — the CLI cannot evict
an in-memory session it does not own, and the table does not claim it does. A blocked or deleted
account still refuses a login *after* its password is verified, so the CLI's answer and the login
route's answer cannot be used to learn whether an account exists.

`delete` is a **soft** delete, so the row, its `app_state`, and its OAuth links survive. Nothing is
lost when an account is removed, and manuscripts stay attributable to the account that wrote them
once documents are owned. A soft-deleted username stays taken, since the row holding it is still
present — which is why `undelete` exists, and why `list` shows deleted rows rather than hiding them:
an account that is deleted and one that never existed are different states, and hiding the first would
make the second look like it.

`--yes` is required on `delete`. It is the one command whose effect an administrator cannot undo by
running its own name again, the username is a bare positional argument, and the cost of a mistyped one
is somebody losing access to their account. Every other command is reversible or self-evidently what it
says.

`undelete` clears `deleted_at` and nothing else. It deliberately does **not** re-arm
`must_change_password` or re-issue a password: the account's credentials survived the delete
untouched, so an undelete restores what was there rather than inventing a new state. It does stamp
`credentials_changed_at`, because a session that predates the delete must not come back to life with
it — otherwise delete followed by undelete would quietly reinstate a session issued while the account
was supposed to be gone.

`AccountStore.from_env()` is removed. It had no callers, and it was wrong twice over: it rooted the
store at `DOCKB_CHAPTERS_DIR` directly rather than through `resolve_document_base_dir`, so it would
have missed the default base directory and the git provisioning the server does, and it raised its own
message for a missing `DOCKB_SECRET_KEY` where the server raises a different one. The CLI resolves the
base directory the same way the server does and reports the same missing-setting errors, so the two
cannot drift.

### Usernames

A username is a name, not an address, and it is the identity key for sessions, cookies and app state
(§3). It is stored lowercased with surrounding whitespace stripped, and is `UNIQUE`.

Normalizing is not cosmetic. SQLite compares `TEXT` case-sensitively, so without it `Brian` and
`brian` would be two accounts — and since the normalized value becomes the document owner, a case
variant would split one person's documents across two owners. The CLI rejects a username that differs
from an existing one only by case or surrounding whitespace.

`email` is a separate, admin-supplied property that is **not verified** and is not an identity. It is
nullable, because a row created by a federated login may lack one, and `UNIQUE`, because
§10 decides accounts are never merged by an address — making the address unique removes the ambiguity
that a merge would have had to resolve. The CLI requires a non-empty address and reports a duplicate
as an error rather than silently refusing it.

Two consequences follow from `UNIQUE`, and both need the other nullable. A row with no password — one
created by a federated login — stores `NULL` rather than `''`, because `NULL`
does not collide under a unique constraint and `''` would. And a person who signs in with a provider
*and* holds a password account cannot have both when the provider reports the same address. §10
already records the cost of not linking accounts; this is a second instance of it.

An existing database may already hold addresses the index refuses, because a local-mode row used to be
written with `''` before local mode was removed, and a provider could report one address twice. The schema migration clears them —
blanks to `NULL`, and among duplicates the earliest row keeps the address — because otherwise the index
cannot be created and the backend will not start. This discards an unverified address, so every affected
account is logged by username for the operator to re-supply through the CLI.

A federated login reporting an address another account already holds is **refused**. The refusal is
raised before anything is written, so a failed attempt leaves neither a `users` row nor a provider
link. An account repeating *its own* address on a later sign-in is not a collision and proceeds.
Locking a person out of DockB over a provider-reported address is the accepted cost of the
constraint; an email the admin supplied can be re-supplied through the CLI, and one a provider
supplied is unverified and therefore not an identity.

### Passwords

- Passwords are stored as **Argon2id** hashes (`argon2-cffi`), not salted SHA-256. The
  parameters come from OWASP's Password Storage Cheat Sheet. One dependency is worth it: the
  endpoint is eventually public, and PBKDF2 is CPU-cost-only, so a GPU cracks it far faster.
  That cheat sheet lists five Argon2id profiles of *equal* defence, differing only in how they
  trade CPU against RAM, so "the OWASP parameters" is not a number and has to be named. DockB
  takes the strongest and the most RAM-hungry of the five, `m=47104` (46 MiB), `t=1`, `p=1`:
  the trade runs the right way for a server, where a login is rare and RAM is not the scarce
  resource. Dropping to `m=19456, t=2, p=1` is an equal-strength change for a small host, and
  is one constant in `passwords.py`.
- The hash is also **peppered** with a key derived from `DOCKB_SECRET_KEY`, keyed in with HMAC
  before Argon2 sees it. Argon2 has no pepper parameter of its own. Without this, a stolen
  `dockb_app.db` is an offline cracking target: the salt is per hash, but it is *stored*, so
  every guess can be tried locally at 46 MiB a time. The pepper is what makes a stolen database
  alone insufficient. It is domain-separated from the Fernet token key, which is
  `sha256(secret)` outright, so the two can be rotated apart.
- The pepper has two costs, both accepted:
  - **`DOCKB_SECRET_KEY` becomes load-bearing.** It cannot be optional, so `wire()`'s current
    habit of substituting an ephemeral secret when it is unset has to stop for password login.
    An ephemeral pepper would differ on every restart and lock every user out.
  - **Rotating it locks everyone out**, because every stored hash was keyed with the old one.
    There is no second factor and no reset over HTTP (§7), so recovery is `dockb users
    set-password`. Token encryption already has this property (`TokenEncryptor.try_decrypt`
    returns `None` after a rotation), so this is not a new class of operational surprise — but
    it is a new way to lose access to accounts, and the two should be rotated separately.
- The verification runs off the event loop. Argon2id is deliberately slow and memory-hard, and
  asyncio is cooperative and single-threaded: a blocking call in an `async def` route stalls
  every concurrent request for its full duration, whether or not it releases the GIL. The login
  route is therefore `async def` and offloads verification with
  `fastapi.concurrency.run_in_threadpool`, leaving the rest of `AuthService` synchronous as it is
  today.
- The offload belongs at that route and nowhere else, because the other caller has no event loop
  to stall: the CLI generates, hashes and resets passwords in a plain synchronous process. So
  `passwords.py` is a synchronous module throughout, and `run_in_threadpool` is applied where the
  asynchronous caller is.
- The not-found path verifies against a precomputed dummy hash, so that a request for a
  non-existent username costs the same as a wrong password. Skipping it is a reliable username
  oracle. The dummy is hashed with **the same Argon2id parameters** as a real one — a cheaper
  dummy reintroduces the timing difference it exists to remove — so the test asserts its
  parameters, not merely that it verifies `False`. It is deliberately *not* peppered: Argon2id
  costs the same whatever it is given, so equalising what a rejection costs does not require
  equalising the secret in front of it, and leaving the dummy a constant means the control does
  not change shape when the pepper does.
- An account with no password at all — a provider-only row, whose `password_hash` is `NULL` — is
  verified against that same dummy rather than rejected early. It has to cost the same too, or
  "this account has no password" becomes a free oracle for anyone who can guess a username.
- For the same reason a **blocked** or **deleted** account is still verified against its own hash
  before the refusal. Turning one away on sight costs nothing, which would make "this account is
  blocked" a free oracle in exactly the way the dummy exists to prevent. The block is checked after
  the password is proved, never instead of it.
- Passwords are compared as submitted, with **no Unicode normalization**, per NIST SP 800-63B:
  normalizing would make a password the person did not choose verify against one they did.
- Login is rate limited per username and per IP, by **exponential backoff** rather than lockout
  (decided). The federated flow never needed this — Google and GitHub did the throttling — and a
  password endpoint has to do it. Backoff, not a lockout, because DockB's user set is small and
  known: a hard lockout is a weapon anyone can point at the one legitimate user, and for a
  single-user install that user is the owner. Backoff slows the same attacker without ever
  closing the door to the person who owns it. Each consecutive failure lengthens the delay, and it
  decays back to zero after a quiet period. Both counters are in-memory and reset on restart,
  matching the existing in-memory `SessionManager`; the limit is therefore per server process,
  not per deployment.
- **A successful login clears both the username and the IP counter.** Someone who fumbles twice
  and then signs in correctly should not be left throttled for the rest of the window.
- The policy is a minimum of 12 characters and a maximum of 128, with no composition rules. NIST
  SP 800-63B prefers length and a blocklist over character classes, and rules about capitals,
  digits and symbols push people toward predictable substitutions. The maximum bounds the Argon2
  cost of an over-long submission, so it is checked *before* hashing rather than after. The
  length is counted in characters, not bytes.
- Refusing to change a password to the one already in force is **not** part of this policy: it
  needs the stored hash and a verification, so it belongs to `AuthService`. The policy itself is
  length only.

### Changing a password

Changing a password requires proving the **current** one (decided), even though the caller already
holds a session. The session is the thing being defended: without the check, anyone who walks up to
an unlocked browser, or who has stolen a session cookie, can change the password and take the account
over permanently — a stolen session that can only read is a much smaller problem than one that can
lock the owner out. It costs one field, and it does not burden the first-use case, because a user
arriving at the change form with `must_change_password` set knows the temporary password they
just signed in with.

Proving the current password means verifying it, not comparing it: a non-empty new password is
rejected when it verifies against the stored hash. That is why the refusal needs the hash and so
belongs to `AuthService` rather than to the policy, which never sees a hash.
- A password that fails the policy raises one error carrying the reason, because the two callers
  render it differently — the CLI to stderr, the route as a client error — and neither should have
  to re-derive which rule was broken.

### Temporary passwords

The CLI generates the temporary password with `secrets`, prints it **once**, and sets
`must_change_password`. It is never logged, and no command takes one as an argument, because an
argument is recorded in the shell history and the process table. There is no way to supply your own:
an administrator who wants to choose a person's first password has them sign in on the generated one
and change it, which is the flow the temporary password exists to start. The generated value is exempt
from the minimum length, since its entropy comes from generation rather than from the person choosing
it.

So the exemption is an argument to the policy check rather than a different policy: a generated
value still has to pass the maximum, and the first thing a user does with a temporary password is
replace it with one that passes the minimum.

An administrator reads it off the console and passes it to the user out of band. It is not emailed,
and the address on the account is not verified, so there is nowhere to send it.

### First use must change the password

`must_change_password` is enforced, not merely displayed. A login on a temporary password succeeds
and mints a session, but the gate then serves **only** the routes needed to get out of the
situation: `POST /api/auth/change-password`, `POST /api/auth/logout`, and `GET /api/auth/me`. Every
manuscript route, and the app-state routes that carry the editor's record, are refused with 403
`password_change_required` until the password changes. A flag that is shown without being enforced
is not a control, and the user would otherwise keep the temporary password indefinitely.

`GET /api/auth/me` is among the three because the editor needs to know *who* it is talking to and
that a change is pending, in order to render the change-password screen at all. It returns
`password_change_required`, and it reads only the account row. It is not a way to the data: every
route that serves a manuscript is still closed.

The change is enforced by `get_current_user`, which is the dependency the manuscript routers are
registered with, so it covers every gated route in one place rather than needing each router to
remember. The three exceptions are the auth router's own routes, which authenticate through
`get_authenticated_user` instead — the same check without the must-change refusal.

### Changing the password ends the session that asked

Setting a password stamps `credentials_changed_at`, and `resolve_session` refuses any session older
than that stamp. This is the CLI's block-and-reset rule (§ *Blocking, deletion, and invalidating a
live session*) applying to the user's own change, and it is left to apply rather than carved out:
one rule, "a credential change ends every session that predates it", is easier to reason about than
one with an exception.

The cost is that a first-time user signs in twice — once on the temporary password, once on the
password they just chose. The change-password route says so in its response (`signed_out: true`) and
the editor presents the sign-in gate again, rather than leaving the user on a page whose every
request is about to fail with 401.

### Blocking, deletion, and invalidating a live session

`blocked_at` and `deleted_at` both refuse a login, and both are re-checked on every gated request
by re-reading the account row. Login reports the same generic failure for a wrong password, an
unknown username, and a blocked account, so the form is not an account-status oracle.

Blocking does **not** work by evicting the session at the moment of the block, because there is no
in-process block to evict from: the only thing that blocks is `dockb users block`, and the CLI is a
separate process from the server that cannot reach the server's in-memory `SessionManager`.

`users.credentials_changed_at` is what actually enforces it, and it covers blocking, deletion and
password resets with a single comparison. The column is stamped whenever a credential is set, reset,
blocked or deleted, and the server compares it against the session's creation time on every request,
refusing an older session. The value lives in the database, so the check works across processes, and
it costs nothing extra because the request already reads the account row to learn whether the
account is blocked.

A refused session is also **dropped**, not just left not resolving. Refusal here is permanent rather
than temporary — a stamp only moves forward, and a block or delete is not undone — so a
`SessionContext` kept in that state could never serve a request again while holding its job queue
and doc cache. The block, delete and reset paths depend on this too, since the CLI that causes them
cannot reach the server's sessions to evict them.

Recording a session's creation time is therefore part of the design rather than an implementation
detail: `SessionManager.create()` has to keep it, or the comparison has nothing to make.

### The session cookie

The session cookie is tightened to `SameSite=Strict` for the password path, where a form post has no
`state` or PKCE to protect it. It is scoped to `/api` (§4) and the editor is served same-origin from
`/editor/` (§6), so a cross-site form post to a gated route carries no cookie.

### Deferred

Multi-factor authentication, recovery of a forgotten password over HTTP, and email verification are
all out of scope. `dockb users set-password` is the only recovery path, which is sufficient while the
user set is small and known, and would not be for untrusted users.

The column-by-column schema and the store's accessors move down to
`src/dockb/infrastructure/accounts/README.md` as the code lands.

## 8. Flow in full (reference)

1. The editor asks `GET /api/auth/config`, which always reports `login_required: true`, and shows
   the Sign-in gate with a username/password form. Provider buttons appear underneath it only when
   `providers` is non-empty.
   - **Password:** the editor posts the username and password to `POST /api/auth/login/password`,
     which verifies the Argon2id hash, starts the server-side session, and sets its own HttpOnly
     session cookie. The response carries the profile and `password_change_required`. A first-time
     user whose `must_change_password` is set is then served only `/api/auth/me`,
     `/api/auth/change-password` and `/api/auth/logout`, and is shown the change-password screen
     until the password changes.
   - **Provider:** the editor asks the backend for a login URL (`GET /api/auth/login?provider=google`),
     which returns the provider consent URL with `state` and a PKCE `code_verifier` the backend
     remembers.
2. The editor opens that URL in the system browser; the user consents.
3. Provider redirects to `http://localhost:{OAUTH_CALLBACK_PORT}/callback?...&code=...`.
4. The backend verifies `state`, exchanges the code (with `code_verifier`), stores the encrypted
   refresh token, upserts the user, and sets its own HttpOnly session cookie.
5. The editor reads that session; every API call after carries it. `GET /api/app/state` and
   `PUT /api/app/state` are then per-user as the UI record requires; `GET /api/auth/me` returns the
   signed-in user's profile and doubles as a session check from the editor.

## 9. Open questions

- **The store layout for per-user document ownership** — when documents become owned by their user
  (§ next cycle), the markdown tree is keyed by title in a shared git repository, so two users
  cannot both hold a document called "Book One". Per-user trees are the decision; whether that means
  one git repository per user, or one repository with per-user subdirectories whose commits and
  history span users, is not yet decided.
- **Documents belonging to a soft-deleted account** — `deleted_at` keeps the row so manuscripts stay
  attributable, but ownership raises what *visible* means. Whether such a document is reassigned,
  shown to an administrator only, or hidden from everyone needs deciding when ownership lands, since
  the answer changes the delete command's contract.

## 10. Resolved questions

Settled while the design was implemented, or decided since:

- **First-run UX** — no session opens the Sign-in gate; after a live session the editor restores
  the last document or shows the select-document modal (`README_markdown_editor_ui.md` §9).
- **Session lifetime** — the session cookie lives for `OAUTH_SESSION_TTL_HOURS` (default 48)
  hours; sessions do not survive a backend restart (the in-memory `SessionManager` does not), and
  a re-login on restart is accepted for the desktop app.
- **SQL storage** — the SQLite store uses the stdlib `sqlite3` module with sync handlers, not
  SQLAlchemy; the store is small, local, and single-process, and an ORM adds nothing there. A
  future Postgres migration re-implements `AccountStore` behind the same interface.
- **State/PKCE memory** — pending login states (with their PKCE verifiers) are valid for 10
  minutes and single-use; storing them alongside the code-swap protects logins against CSRF and
  code-swapping, matching the security goals in §4.
- **Every user signs in** — there is no local mode; `requires_login` is unconditionally true and no
  environment variable can make a gated route serve an unauthenticated caller (§6).
- **Account linking** — not supported. Every provider account, and every password account, is its
  own `users` row, and accounts are never merged by email. Linking on a verified email is an
  account-takeover vector: an attacker registers the victim's address first, and when the victim
  later signs in with a federated provider under that same address, a naive merge hands them the
  attacker's account. Doing no linking means the vector does not exist; the cost is that one person
  using two providers has two accounts.
- **Machine-to-machine credentials are separate from user accounts** — the MCP server's service
  credential is not a user account and never appears in `users`. It is a per-prompt bearer token
  held in memory, and is documented in `README_mcp_auth.md`.
