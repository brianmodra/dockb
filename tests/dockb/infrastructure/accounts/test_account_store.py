"""Tests for AccountStore — SQLite accounts, OAuth links (encrypted tokens), and app state.

Identities are usernames: ``create_user``/``get_user``/``upsert_provider_user`` and the
app-state accessors are keyed by the unique ``users.username`` column.
"""

from __future__ import annotations

from dockb.infrastructure.accounts.store import AccountStore, TokenEncryptor

_SECRET = "test-secret-key"
_PROVIDER = "google"
_ACCOUNT_ID = "goog-123"
_USERNAME = "abby"
_EMAIL = "abby@example.com"
_REFRESH_TOKEN = "super-secret-refresh-token-12345"


def _store(tmp_path) -> AccountStore:
    return AccountStore(base_dir=tmp_path, secret=_SECRET)


# ---------------------------------------------------------------- users


def test_create_user_returns_username(tmp_path) -> None:
    store = _store(tmp_path)
    username = store.create_user(_USERNAME, email=_EMAIL, display_name="Abby", avatar_url="http://img/a.png")
    assert username == _USERNAME
    row = store.get_user(username)
    assert row is not None
    assert row["email"] == _EMAIL
    assert row["display_name"] == "Abby"
    assert row["avatar_url"] == "http://img/a.png"


def test_get_user_missing_returns_none(tmp_path) -> None:
    assert _store(tmp_path).get_user("nope") is None


def test_get_user_by_provider_account_missing_returns_none(tmp_path) -> None:
    assert _store(tmp_path).get_user_by_provider_account(_PROVIDER, _ACCOUNT_ID) is None


def test_upsert_provider_user_creates_and_links_on_first_login(tmp_path) -> None:
    store = _store(tmp_path)
    username = store.upsert_provider_user(
        _PROVIDER, _ACCOUNT_ID, username=_USERNAME, email=_EMAIL, display_name="Abby", avatar_url="", token=_REFRESH_TOKEN
    )
    assert username == _USERNAME
    row = store.get_user_by_provider_account(_PROVIDER, _ACCOUNT_ID)
    assert row is not None
    assert row["id"] is not None
    assert row["username"] == _USERNAME
    assert row["email"] == _EMAIL
    account = store.get_provider_account(_PROVIDER, _ACCOUNT_ID)
    assert account is not None
    assert account["token"] == _REFRESH_TOKEN


def test_upsert_provider_user_updates_profile_on_second_login(tmp_path) -> None:
    store = _store(tmp_path)
    first = store.upsert_provider_user(_PROVIDER, _ACCOUNT_ID, username=_USERNAME, email=_EMAIL, display_name="Abby", avatar_url="")
    second = store.upsert_provider_user(
        _PROVIDER, _ACCOUNT_ID, username=_USERNAME, email=_EMAIL, display_name="Abigail", avatar_url="http://img/new.png"
    )
    assert first == second
    row = store.get_user(second)
    assert row is not None
    assert row["username"] == _USERNAME
    assert row["display_name"] == "Abigail"
    assert row["avatar_url"] == "http://img/new.png"


def test_get_user_by_provider_account_round_trip(tmp_path) -> None:
    store = _store(tmp_path)
    store.create_user(_USERNAME, email=_EMAIL, display_name="Abby", avatar_url="")
    store.link_provider_account(_USERNAME, _PROVIDER, _ACCOUNT_ID)
    row = store.get_user_by_provider_account(_PROVIDER, _ACCOUNT_ID)
    assert row is not None
    assert row["username"] == _USERNAME
    assert row["email"] == _EMAIL


def test_get_or_create_local_user_creates_row(tmp_path) -> None:
    store = _store(tmp_path)
    username = store.get_or_create_local_user("brian")
    assert username == "brian"
    row = store.get_user("brian")
    assert row is not None
    assert row["username"] == "brian"
    assert row["display_name"] == "brian"
    assert row["email"] == ""


def test_get_or_create_local_user_is_idempotent(tmp_path) -> None:
    store = _store(tmp_path)
    first = store.get_or_create_local_user("brian")
    second = store.get_or_create_local_user("brian")
    assert first == second == "brian"
    rows = store._connect().execute("SELECT COUNT(*) AS n FROM users WHERE username = ?", ("brian",)).fetchone()
    assert rows["n"] == 1


# ----------------------------------------------------------- oauth links


def test_link_provider_account_stores_encrypted_token(tmp_path) -> None:
    store = _store(tmp_path)
    store.create_user(_USERNAME, email=_EMAIL, display_name="Abby", avatar_url="")
    store.link_provider_account(_USERNAME, _PROVIDER, _ACCOUNT_ID, token=_REFRESH_TOKEN)
    row = store.get_provider_account(_PROVIDER, _ACCOUNT_ID)
    assert row is not None
    assert row["token"] == _REFRESH_TOKEN


def test_provider_account_token_is_not_plaintext_on_disk(tmp_path) -> None:
    store = _store(tmp_path)
    store.create_user(_USERNAME, email=_EMAIL, display_name="Abby", avatar_url="")
    store.link_provider_account(_USERNAME, _PROVIDER, _ACCOUNT_ID, token=_REFRESH_TOKEN)
    raw = (tmp_path / "dockb_app.db").read_bytes()
    assert _REFRESH_TOKEN.encode() not in raw


def test_link_provider_account_upserts_same_account(tmp_path) -> None:
    store = _store(tmp_path)
    store.create_user(_USERNAME, email=_EMAIL, display_name="Abby", avatar_url="")
    store.link_provider_account(_USERNAME, _PROVIDER, _ACCOUNT_ID, token="token-v1")
    store.link_provider_account(_USERNAME, _PROVIDER, _ACCOUNT_ID, token="token-v2")
    row = store.get_provider_account(_PROVIDER, _ACCOUNT_ID)
    assert row is not None
    assert row["token"] == "token-v2"


def test_get_provider_account_without_token_row_tokens_none(tmp_path) -> None:
    store = _store(tmp_path)
    store.create_user(_USERNAME, email=_EMAIL, display_name="Abby", avatar_url="")
    store.link_provider_account(_USERNAME, _PROVIDER, _ACCOUNT_ID)
    row = store.get_provider_account(_PROVIDER, _ACCOUNT_ID)
    assert row is not None
    assert row["token"] is None


# ------------------------------------------------------------- app state


def test_app_state_round_trip(tmp_path) -> None:
    store = _store(tmp_path)
    store.create_user(_USERNAME, email=_EMAIL, display_name="Abby", avatar_url="")
    store.set_app_state(_USERNAME, {"last_document_id": "doc-1", "panel_widths": "{}", "edit_mode": "wysiwyg"})
    state = store.get_app_state(_USERNAME)
    assert state is not None
    assert state["last_document_id"] == "doc-1"
    assert state["panel_widths"] == "{}"
    assert state["edit_mode"] == "wysiwyg"


def test_app_state_works_for_local_user_without_oauth(tmp_path) -> None:
    store = _store(tmp_path)
    store.get_or_create_local_user("brian")
    store.set_app_state("brian", {"last_document_id": "doc-1"})
    state = store.get_app_state("brian")
    assert state is not None
    assert state["last_document_id"] == "doc-1"


def test_app_state_missing_returns_none(tmp_path) -> None:
    assert _store(tmp_path).get_app_state("no-user") is None


def test_cascade_delete_removes_oauth_and_app_state(tmp_path) -> None:
    store = _store(tmp_path)
    store.create_user(_USERNAME, email=_EMAIL, display_name="Abby", avatar_url="")
    store.link_provider_account(_USERNAME, _PROVIDER, _ACCOUNT_ID, token=_REFRESH_TOKEN)
    store.set_app_state(_USERNAME, {"edit_mode": "raw"})
    store._connect().execute("DELETE FROM users WHERE username = ?", (_USERNAME,)).connection.commit()
    assert store.get_provider_account(_PROVIDER, _ACCOUNT_ID) is None
    assert store.get_app_state(_USERNAME) is None


def test_app_state_upserts(tmp_path) -> None:
    store = _store(tmp_path)
    store.create_user(_USERNAME, email=_EMAIL, display_name="Abby", avatar_url="")
    store.set_app_state(_USERNAME, {"edit_mode": "raw"})
    store.set_app_state(_USERNAME, {"edit_mode": "wysiwyg"})
    state = store.get_app_state(_USERNAME)
    assert state is not None
    assert state["edit_mode"] == "wysiwyg"


# ------------------------------------------------------------ encryption


def test_token_encryptor_round_trip() -> None:
    encryptor = TokenEncryptor(_SECRET)
    ciphertext = encryptor.encrypt(_REFRESH_TOKEN)
    assert encryptor.decrypt(ciphertext) == _REFRESH_TOKEN


def test_token_encryptor_different_secret_fails() -> None:
    other = TokenEncryptor("a-different-secret")
    ciphertext = TokenEncryptor(_SECRET).encrypt(_REFRESH_TOKEN)
    assert other.try_decrypt(ciphertext) is None


def test_token_encryptor_is_non_deterministic() -> None:
    encryptor = TokenEncryptor(_SECRET)
    assert encryptor.encrypt(_REFRESH_TOKEN) != encryptor.encrypt(_REFRESH_TOKEN)
