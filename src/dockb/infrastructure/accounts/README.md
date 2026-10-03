# Accounts

## Executive Summary

The backend's server-owned account data, in one SQLite file: the users, their linked
OAuth provider accounts, and each user's editor state. Accounts are not part of the
document graph, so they live in their own relational store rather than in Neo4j. For why
the store is SQLite, why accounts are never merged, and how the local-mode and
account-lifecycle decisions bear on it, see `README_auth.md` at the repository root.

## Package Structure

```
infrastructure/accounts/
├── README.md               # This file
├── __init__.py
└── store.py                # AccountStore, TokenEncryptor, and the schema
```

## The store

`AccountStore` (`src/dockb/infrastructure/accounts/store.py`) owns one `dockb_app.db`
file. Its location is the backend's owned markdown tree — `DOCKB_CHAPTERS_DIR`, resolved
by `resolve_document_base_dir` in `composition.py` and created (and git-initialised) when
missing — so all server-owned on-disk state sits in one place.

It is the stdlib `sqlite3` module, with no ORM, and every value is bound as a query
parameter. Each accessor opens a connection, ensures the schema, and closes it in a
`finally`. `PRAGMA foreign_keys = ON` is set per connection, so hard-deleting a user
cascades to its OAuth links and app state; accounts are in practice soft-deleted, which
deliberately does not cascade.

`AccountStore.from_env()` builds the store from `DOCKB_CHAPTERS_DIR` and
`DOCKB_SECRET_KEY`, and raises if either is missing.

## Schema

Three tables, declared in `_SCHEMA` and created on every connection, then brought up to
`_SCHEMA_VERSION` by the migrations below.

### `users`

| Column | Type | Notes |
| --- | --- | --- |
| `id` | TEXT | Internal UUID. Exists only as the `oauth_accounts` foreign key target. |
| `username` | TEXT | `UNIQUE`, and the identity used everywhere else. |
| `email` | TEXT | `UNIQUE` and nullable. CLI-supplied, or from a provider profile. |
| `display_name` | TEXT | User-facing name. |
| `avatar_url` | TEXT | Profile image URL. |
| `password_hash` | TEXT | Argon2id hash. `NULL` for an account that has only ever signed in through a provider. |
| `must_change_password` | INTEGER | Set when a generated temporary password is outstanding. |
| `blocked_at` | TEXT | When the account was blocked; `NULL` if it is not. |
| `last_login_at` | TEXT | Stamped by `record_login`. |
| `credentials_changed_at` | TEXT | Stamped by every credential or lifecycle change. |
| `deleted_at` | TEXT | Set by a soft delete. |
| `created_at` | TEXT | `CURRENT_TIMESTAMP` default. |

Identity is the `username`, not the `id`: sessions, cookies, and app state all carry it.
Every accessor normalizes it with `strip().lower()`, so `Brian`, `brian` and ` Brian ` are
one account.

`must_change_password` is what gates the UI after a first sign-in with a CLI-generated
password. `credentials_changed_at` is what invalidates sessions that the CLI cannot reach,
because it runs in another process from the server's in-memory session manager; it is
compared as text against a session's creation time, so `_now()` is a fixed-width
`isoformat(timespec="microseconds")` — a variable width would sort wrongly against
`CURRENT_TIMESTAMP`, which resolves only to the second.

`get_or_create_local_user` inserts a minimal row with no password and no provider account
behind it: display name = username, `email` `NULL`, avatar empty. `email` is `NULL` and
never `''`, because `''` would collide with itself under the unique index.

### `oauth_accounts`

| Column | Type | Notes |
| --- | --- | --- |
| `provider` | TEXT | `google`, `github`, … |
| `provider_account_id` | TEXT | The provider's own account id. |
| `user_id` | TEXT | FK to `users.id`, `ON DELETE CASCADE`. |
| `token` | BLOB | The refresh token, Fernet-encrypted. |
| `expires_at` | TEXT | ISO-8601 expiry of that token. |

Composite primary key `(provider, provider_account_id)`. `upsert_provider_user` and
`link_provider_account` both write through an `ON CONFLICT … DO UPDATE`, so a repeat
login refreshes the profile and rotates the token in place. Rows are never merged across
providers: one provider account is one `users` row, and linking by email is deliberately
not done (`README_auth.md` §10).

`upsert_provider_user` refuses, before writing anything, when the reported address is
already held by a *different* account — the unique index would otherwise surface it as an
opaque `IntegrityError` halfway through the write. The same account repeating its own
address is fine.

## Migrations

`PRAGMA user_version`, an integer in the file header, records how far a database has been
taken, so there is no second bookkeeping table. A database that did not exist is stamped at
the current version after `_SCHEMA`; an existing one is stepped through `_MIGRATIONS`.

Each step stamps its version only after it succeeds, so a step failing halfway leaves the
file at the previous version and the retry finishes the job rather than failing on a
duplicate column.

Version 2 added the credential, blocking and deletion columns. It had to resolve the
addresses that the new unique index refuses first, because `get_or_create_local_user` used
to write `''` and a provider could report one address twice: blanks become `NULL`, and
among duplicates the earliest row keeps the address and the rest are nulled. That silently
loses an unverified address, so each affected account is logged by username for the
operator to re-supply through the CLI.

The unique email index is a named statement rather than an inline `UNIQUE` on the column,
because SQLite cannot add a constraint with `ALTER TABLE`. It cannot live in `_SCHEMA`
either — that runs before the migration, so it would be attempted before the duplicates it
refuses are gone.

### `app_state`

| Column | Type | Notes |
| --- | --- | --- |
| `username` | TEXT | Primary key, and FK to `users.username`, `ON DELETE CASCADE`. |
| `last_document_id` | TEXT | The document the editor last had open. |
| `panel_widths` | TEXT | Free-form JSON object, opaque to the backend. |
| `edit_mode` | TEXT | Open string. |
| `updated_at` | TEXT | `CURRENT_TIMESTAMP` default. |

`set_app_state` replaces the row wholesale, so the three fields are a snapshot rather
than a merge.

## Account lifecycle

The password-login work adds the store's half of a lifecycle that `README_auth.md` §7
specifies; the other half — hashing, verification, sessions — is in `AuthService`, not here.

- `create_user(username, …)` — insert a CLI-created account, `UNIQUE` violations on
  `username` and `email` raised as `UsernameTakenError` and `EmailTakenError`.
- `get_credentials(username)` — the hash, `must_change_password`, `blocked_at` and
  `deleted_at` needed to decide whether a sign-in may proceed. Kept apart from
  `get_user` so the lifecycle state cannot be read from a listing.
- `set_password_hash`, `record_login`, `block_user`, `unblock_user`,
  `soft_delete_user` — each writes its own complete `UPDATE` and raises
  `UnknownUserError` when no row matched, so a mistyped username in the CLI is reported
  rather than silently doing nothing.
- `list_users()` — every account without hashes or ids.

`unblock_user` deliberately does not stamp `credentials_changed_at`: blocking already
evicted the account's sessions, so there is nothing left to invalidate.

## Token encryption

`TokenEncryptor` encrypts refresh tokens at rest with a Fernet key derived by SHA-256
from the server secret (`DOCKB_SECRET_KEY`). `oauth_accounts.token` is therefore never
plaintext, and this store is a credential store and is treated as one.

- `encrypt(token) -> bytes`
- `decrypt(ciphertext) -> str` — raises `InvalidToken` on failure.
- `try_decrypt(ciphertext) -> str | None` — None when the key does not match, which is
  what happens after `DOCKB_SECRET_KEY` is rotated: existing rows can no longer be read.

`get_provider_account` decrypts on the way out, so a plaintext token is only ever in
memory at the point of use.

## Moving off SQLite

The store is small, local, and single-process, which is why it is `sqlite3` rather than
an ORM. Postgres later means re-implementing `AccountStore` against a new driver; the
interface and the route call sites in `controllers/auth.py` and `controllers/app_state.py`
do not change.
