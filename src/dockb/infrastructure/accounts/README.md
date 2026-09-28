# Accounts

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
`finally`. `PRAGMA foreign_keys = ON` is set per connection, so deleting a user cascades
to its OAuth links and app state.

`AccountStore.from_env()` builds the store from `DOCKB_CHAPTERS_DIR` and
`DOCKB_SECRET_KEY`, and raises if either is missing.

## Schema

Three tables, declared in `_SCHEMA` and created on every connection.

### `users`

| Column | Type | Notes |
| --- | --- | --- |
| `id` | TEXT | Internal UUID. Exists only as the `oauth_accounts` foreign key target. |
| `username` | TEXT | `UNIQUE`, and the identity used everywhere else. |
| `email` | TEXT | From the provider profile. |
| `display_name` | TEXT | User-facing name. |
| `avatar_url` | TEXT | Profile image URL. |
| `created_at` | TEXT | `CURRENT_TIMESTAMP` default. |

Identity is the `username`, not the `id`: sessions, cookies, and app state all carry it.
It is the OS username in local mode and the OAuth profile username otherwise, so
`get_or_create_local_user` inserts a minimal row (display name = username, empty email and
avatar) with no provider account behind it.

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
