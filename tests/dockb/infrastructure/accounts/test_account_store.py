"""Tests for AccountStore — SQLite accounts, OAuth links (encrypted tokens), and app state."""

from __future__ import annotations

from dockb.infrastructure.accounts.store import AccountStore, TokenEncryptor

_SECRET = "test-secret-key"
_PROVIDER = "google"
_ACCOUNT_ID = "goog-123"
_EMAIL = "abby@example.com"
_REFRESH_TOKEN = "super-secret-refresh-token-12345"


def _store(tmp_path) -> AccountStore:
    return AccountStore(base_dir=tmp_path, secret=_SECRET)


# ---------------------------------------------------------------- users


def test_create_user_returns_id(tmp_path) -> None:
    store = _store(tmp_path)
    user_id = store.create_user(email=_EMAIL, display_name="Abby", avatar_url="http://img/a.png")
    assert user_id
    row = store.get_user(user_id)
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
    user_id = store.upsert_provider_user(_PROVIDER, _ACCOUNT_ID, email=_EMAIL, display_name="Abby", avatar_url="", token=_REFRESH_TOKEN)
    assert user_id
    row = store.get_user_by_provider_account(_PROVIDER, _ACCOUNT_ID)
    assert row is not None
    assert row["id"] == user_id
    assert row["email"] == _EMAIL
    account = store.get_provider_account(_PROVIDER, _ACCOUNT_ID)
    assert account is not None
    assert account["token"] == _REFRESH_TOKEN


def test_upsert_provider_user_updates_profile_on_second_login(tmp_path) -> None:
    store = _store(tmp_path)
    first = store.upsert_provider_user(_PROVIDER, _ACCOUNT_ID, email=_EMAIL, display_name="Abby", avatar_url="")
    second = store.upsert_provider_user(_PROVIDER, _ACCOUNT_ID, email=_EMAIL, display_name="Abigail", avatar_url="http://img/new.png")
    assert first == second
    row = store.get_user(second)
    assert row is not None
    assert row["display_name"] == "Abigail"
    assert row["avatar_url"] == "http://img/new.png"


def test_get_user_by_provider_account_round_trip(tmp_path) -> None:
    store = _store(tmp_path)
    user_id = store.create_user(email=_EMAIL, display_name="Abby", avatar_url="")
    store.link_provider_account(user_id, _PROVIDER, _ACCOUNT_ID)
    row = store.get_user_by_provider_account(_PROVIDER, _ACCOUNT_ID)
    assert row is not None
    assert row["id"] == user_id
    assert row["email"] == _EMAIL


# ----------------------------------------------------------- oauth links


def test_link_provider_account_stores_encrypted_token(tmp_path) -> None:
    store = _store(tmp_path)
    user_id = store.create_user(email=_EMAIL, display_name="Abby", avatar_url="")
    store.link_provider_account(user_id, _PROVIDER, _ACCOUNT_ID, token=_REFRESH_TOKEN)
    row = store.get_provider_account(_PROVIDER, _ACCOUNT_ID)
    assert row is not None
    assert row["token"] == _REFRESH_TOKEN
    assert row["user_id"] == user_id


def test_provider_account_token_is_not_plaintext_on_disk(tmp_path) -> None:
    store = _store(tmp_path)
    user_id = store.create_user(email=_EMAIL, display_name="Abby", avatar_url="")
    store.link_provider_account(user_id, _PROVIDER, _ACCOUNT_ID, token=_REFRESH_TOKEN)
    raw = (tmp_path / "dockb_app.db").read_bytes()
    assert _REFRESH_TOKEN.encode() not in raw


def test_link_provider_account_upserts_same_account(tmp_path) -> None:
    store = _store(tmp_path)
    user_id = store.create_user(email=_EMAIL, display_name="Abby", avatar_url="")
    store.link_provider_account(user_id, _PROVIDER, _ACCOUNT_ID, token="token-v1")
    store.link_provider_account(user_id, _PROVIDER, _ACCOUNT_ID, token="token-v2")
    row = store.get_provider_account(_PROVIDER, _ACCOUNT_ID)
    assert row is not None
    assert row["token"] == "token-v2"


def test_get_provider_account_without_token_row_tokens_none(tmp_path) -> None:
    store = _store(tmp_path)
    user_id = store.create_user(email=_EMAIL, display_name="Abby", avatar_url="")
    store.link_provider_account(user_id, _PROVIDER, _ACCOUNT_ID)
    row = store.get_provider_account(_PROVIDER, _ACCOUNT_ID)
    assert row is not None
    assert row["token"] is None


# ------------------------------------------------------------- app state


def test_app_state_round_trip(tmp_path) -> None:
    store = _store(tmp_path)
    user_id = store.create_user(email=_EMAIL, display_name="Abby", avatar_url="")
    store.set_app_state(user_id, {"last_document_id": "doc-1", "panel_widths": "{}", "edit_mode": "wysiwyg"})
    state = store.get_app_state(user_id)
    assert state is not None
    assert state["last_document_id"] == "doc-1"
    assert state["panel_widths"] == "{}"
    assert state["edit_mode"] == "wysiwyg"


def test_app_state_missing_returns_none(tmp_path) -> None:
    assert _store(tmp_path).get_app_state("no-user") is None


def test_cascade_delete_removes_oauth_and_app_state(tmp_path) -> None:
    store = _store(tmp_path)
    user_id = store.create_user(email=_EMAIL, display_name="Abby", avatar_url="")
    store.link_provider_account(user_id, _PROVIDER, _ACCOUNT_ID, token=_REFRESH_TOKEN)
    store.set_app_state(user_id, {"edit_mode": "raw"})
    store._connect().execute("DELETE FROM users WHERE id = ?", (user_id,)).connection.commit()
    assert store.get_provider_account(_PROVIDER, _ACCOUNT_ID) is None
    assert store.get_app_state(user_id) is None


def test_app_state_upserts(tmp_path) -> None:
    store = _store(tmp_path)
    user_id = store.create_user(email=_EMAIL, display_name="Abby", avatar_url="")
    store.set_app_state(user_id, {"edit_mode": "raw"})
    store.set_app_state(user_id, {"edit_mode": "wysiwyg"})
    state = store.get_app_state(user_id)
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
