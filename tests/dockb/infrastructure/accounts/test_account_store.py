"""Tests for AccountStore — SQLite accounts, OAuth links (encrypted tokens), and app state.

Identities are usernames: ``create_user``/``get_user``/``upsert_provider_user`` and the
app-state accessors are keyed by the unique ``users.username`` column. That column is
normalized, so ``Brian``, `` brian `` and ``brian`` are one account and not three.
"""

from __future__ import annotations

import logging
import sqlite3

import pytest

from dockb.infrastructure.accounts.store import (
    _SCHEMA_VERSION,
    AccountStore,
    EmailTakenError,
    TokenEncryptor,
    UnknownUserError,
    UsernameTakenError,
    _now,
)

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


def test_app_state_works_for_a_password_user_without_oauth(tmp_path) -> None:
    store = _store(tmp_path)
    store.create_user("brian", email=None, display_name="Brian")
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


# -------------------------------------------------- migrations and version


_CREDENTIAL_COLUMNS = (
    "password_hash",
    "must_change_password",
    "blocked_at",
    "last_login_at",
    "credentials_changed_at",
    "deleted_at",
)

# The users table as it stood before credentials existed.
_LEGACY_USERS = """
CREATE TABLE users (
    id            TEXT PRIMARY KEY,
    username      TEXT NOT NULL UNIQUE,
    email         TEXT,
    display_name  TEXT,
    avatar_url    TEXT,
    created_at    TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""


def _legacy_database(tmp_path, rows: tuple[tuple[str, str], ...] = ()) -> None:
    """Write a pre-credentials ``dockb_app.db``, as released before this change."""
    connection = sqlite3.connect(tmp_path / "dockb_app.db")
    connection.executescript(_LEGACY_USERS)
    for username, email in rows:
        connection.execute(
            "INSERT INTO users (id, username, email, display_name, avatar_url) VALUES (?, ?, ?, ?, '')",
            (f"id-{username}", username, email, username),
        )
    connection.commit()
    connection.close()


def _column_names(tmp_path) -> set[str]:
    connection = sqlite3.connect(tmp_path / "dockb_app.db")
    try:
        return {row[1] for row in connection.execute("PRAGMA table_info(users)")}
    finally:
        connection.close()


def _user_version(tmp_path) -> int:
    connection = sqlite3.connect(tmp_path / "dockb_app.db")
    try:
        return connection.execute("PRAGMA user_version").fetchone()[0]
    finally:
        connection.close()


def _has_named_email_index(tmp_path) -> bool:
    connection = sqlite3.connect(tmp_path / "dockb_app.db")
    try:
        row = connection.execute("SELECT 1 FROM sqlite_master WHERE type = 'index' AND name = 'users_email_unique'").fetchone()
    finally:
        connection.close()
    return row is not None


def test_fresh_database_has_credential_columns(tmp_path) -> None:
    _store(tmp_path).get_user("anyone")
    assert set(_CREDENTIAL_COLUMNS) <= _column_names(tmp_path)


def test_fresh_database_is_stamped_at_the_current_version(tmp_path) -> None:
    _store(tmp_path).get_user("anyone")
    assert _user_version(tmp_path) == _SCHEMA_VERSION


def test_migration_adds_credential_columns_to_an_existing_database(tmp_path) -> None:
    _legacy_database(tmp_path, (("abby", _EMAIL),))
    assert not set(_CREDENTIAL_COLUMNS) & _column_names(tmp_path)
    row = _store(tmp_path).get_user("abby")
    assert row is not None and row["email"] == _EMAIL
    assert set(_CREDENTIAL_COLUMNS) <= _column_names(tmp_path)
    assert _user_version(tmp_path) == _SCHEMA_VERSION


def test_migration_keeps_existing_rows_and_their_credentials(tmp_path) -> None:
    _legacy_database(tmp_path, (("abby", _EMAIL),))
    store = _store(tmp_path)
    store.set_password_hash("abby", "a-hash", must_change_password=True)
    row = store.get_user("abby")
    assert row is not None and row["password_hash"] == "a-hash"
    assert row["must_change_password"] == 1


def test_migration_resolves_blank_and_duplicate_emails(tmp_path) -> None:
    # A password account can have no address, and a provider can report one address twice,
    # either of which would make the unique index fail and stop the backend starting.
    _legacy_database(tmp_path, (("abby", ""), ("brian", "same@example.com"), ("carol", "same@example.com")))
    store = _store(tmp_path)
    earliest = store.get_user("brian")
    assert earliest is not None and earliest["email"] == "same@example.com"
    assert store.get_user("abby")["email"] is None
    assert store.get_user("carol")["email"] is None
    # The surviving address is now protected, so a new account cannot take it.
    with pytest.raises(EmailTakenError):
        store.create_user("dave", email="same@example.com", display_name="Dave")
    assert store.get_user("dave") is None


def test_migration_warns_about_each_account_it_clears(tmp_path, caplog) -> None:
    # The addresses are deleted with no other trace, so the operator has to be told
    # which ones need re-supplying through the CLI.
    _legacy_database(tmp_path, (("abby", ""), ("brian", "same@example.com"), ("carol", "same@example.com")))
    with caplog.at_level(logging.WARNING, logger="dockb.infrastructure.accounts.store"):
        _store(tmp_path).get_user("brian")
    cleared = {record.args[0] for record in caplog.records if record.levelno >= logging.WARNING}
    assert cleared == {"abby", "carol"}


def test_migration_is_idempotent(tmp_path) -> None:
    _legacy_database(tmp_path, (("abby", _EMAIL),))
    store = _store(tmp_path)
    for _ in range(3):
        assert store.get_user("abby") is not None
    assert _user_version(tmp_path) == _SCHEMA_VERSION


def test_a_fresh_and_a_migrated_database_name_the_email_index_alike(tmp_path) -> None:
    # The index cannot be declared inline on the column, because SQLite cannot add a
    # constraint with ALTER TABLE, so it is created as a named statement. Whichever
    # database shape created it, both should end up naming it the same way.
    fresh = tmp_path / "fresh"
    fresh.mkdir()
    _store(fresh).get_user("anyone")
    migrated = tmp_path / "migrated"
    migrated.mkdir()
    _legacy_database(migrated, (("abby", _EMAIL),))
    _store(migrated).get_user("abby")
    assert _has_named_email_index(fresh)
    assert _has_named_email_index(migrated)


# -------------------------------------------------- username normalization


def test_create_user_normalizes_the_username(tmp_path) -> None:
    username = _store(tmp_path).create_user("  Brian  ", email=_EMAIL, display_name="Brian")
    assert username == "brian"
    assert _store(tmp_path).get_user("brian") is not None


def test_get_user_matches_the_normalized_username(tmp_path) -> None:
    store = _store(tmp_path)
    store.create_user("brian", email=_EMAIL, display_name="Brian")
    assert store.get_user("BRIAN") is not None
    assert store.get_user(" Brian ") is not None


def test_username_differing_only_by_case_is_taken(tmp_path) -> None:
    store = _store(tmp_path)
    store.create_user("brian", email=_EMAIL, display_name="Brian")
    with pytest.raises(UsernameTakenError):
        store.create_user("BRIAN", email="other@example.com", display_name="Brian")


def test_username_differing_only_by_whitespace_is_taken(tmp_path) -> None:
    store = _store(tmp_path)
    store.create_user("brian", email=_EMAIL, display_name="Brian")
    with pytest.raises(UsernameTakenError):
        store.create_user(" brian ", email="other@example.com", display_name="Brian")


def test_upsert_provider_user_normalizes_the_username(tmp_path) -> None:
    username = _store(tmp_path).upsert_provider_user(
        _PROVIDER, _ACCOUNT_ID, username="  Brian  ", email=_EMAIL, display_name="Brian", avatar_url=""
    )
    assert username == "brian"


def test_upsert_provider_user_accepts_a_provider_with_no_email(tmp_path) -> None:
    # §7 makes email nullable precisely because a provider profile may lack one.
    store = _store(tmp_path)
    store.upsert_provider_user(_PROVIDER, _ACCOUNT_ID, username=_USERNAME, email=None, display_name="Abby", avatar_url="")
    assert store.get_user(_USERNAME)["email"] is None


def test_upsert_provider_user_refuses_a_duplicate_email(tmp_path) -> None:
    store = _store(tmp_path)
    store.create_user("brian", email=_EMAIL, display_name="Brian")
    with pytest.raises(EmailTakenError):
        store.upsert_provider_user("github", "gh-999", username="alex", email=_EMAIL, display_name="Alex", avatar_url="")


def test_refused_duplicate_email_login_leaves_no_partial_account(tmp_path) -> None:
    # The refusal must happen before anything is written, or the store keeps a users
    # row with no provider account behind it and no way to sign in.
    store = _store(tmp_path)
    store.create_user("brian", email=_EMAIL, display_name="Brian")
    with pytest.raises(EmailTakenError):
        store.upsert_provider_user("github", "gh-999", username="alex", email=_EMAIL, display_name="Alex", avatar_url="")
    assert store.get_user("alex") is None
    assert store.get_provider_account("github", "gh-999") is None


def test_a_second_login_may_repeat_its_own_email(tmp_path) -> None:
    # Refusing a repeat of the account's *own* address would lock the user out on
    # every sign-in after the first.
    store = _store(tmp_path)
    first = store.upsert_provider_user(_PROVIDER, _ACCOUNT_ID, username=_USERNAME, email=_EMAIL, display_name="Abby", avatar_url="")
    second = store.upsert_provider_user(_PROVIDER, _ACCOUNT_ID, username=_USERNAME, email=_EMAIL, display_name="Abigail", avatar_url="")
    assert first == second


# ------------------------------------------------------------------- email


def test_two_accounts_may_both_have_no_email(tmp_path) -> None:
    store = _store(tmp_path)
    store.create_user("brian", email=None, display_name="Brian")
    store.create_user("alex", email=None, display_name="Alex")
    assert store.get_user("brian")["email"] is None
    assert store.get_user("alex")["email"] is None


def test_duplicate_email_is_rejected(tmp_path) -> None:
    store = _store(tmp_path)
    store.create_user("brian", email=_EMAIL, display_name="Brian")
    with pytest.raises(EmailTakenError):
        store.create_user("alex", email=_EMAIL, display_name="Alex")


def test_an_absent_email_is_null_not_an_empty_string(tmp_path) -> None:
    # '' would collide with another '' under the unique constraint; NULL does not.
    store = _store(tmp_path)
    store.create_user("brian", email=None, display_name="Brian")
    assert store.get_user("brian")["email"] is None
    store.create_user("alex", email=None, display_name="Alex")
    assert store.get_user("alex")["email"] is None


# ------------------------------------------------------------- credentials


def test_get_credentials_reports_the_sign_in_state(tmp_path) -> None:
    store = _store(tmp_path)
    store.create_user("brian", email=_EMAIL, display_name="Brian", password_hash="a-hash", must_change_password=True)
    credentials = store.get_credentials("brian")
    assert credentials is not None
    assert credentials["password_hash"] == "a-hash"
    assert credentials["must_change_password"] == 1
    assert credentials["blocked_at"] is None
    assert credentials["deleted_at"] is None


def test_get_credentials_missing_account_returns_none(tmp_path) -> None:
    assert _store(tmp_path).get_credentials("nope") is None


def test_get_credentials_never_carries_the_oauth_token(tmp_path) -> None:
    store = _store(tmp_path)
    store.upsert_provider_user(
        _PROVIDER, _ACCOUNT_ID, username=_USERNAME, email=_EMAIL, display_name="Abby", avatar_url="", token=_REFRESH_TOKEN
    )
    assert "token" not in store.get_credentials(_USERNAME)


def test_set_password_hash_stamps_credentials_changed_at(tmp_path) -> None:
    store = _store(tmp_path)
    store.create_user("brian", email=_EMAIL, display_name="Brian")
    assert store.get_user("brian")["credentials_changed_at"] is None
    store.set_password_hash("brian", "a-hash")
    assert store.get_user("brian")["credentials_changed_at"] is not None


def test_credentials_changed_at_distinguishes_two_changes_in_the_same_second(tmp_path) -> None:
    # It is compared against a session's creation time to invalidate sessions the CLI
    # cannot reach, so second resolution would let a session created moments earlier
    # compare equal and survive a password reset.
    store = _store(tmp_path)
    store.create_user("brian", email=_EMAIL, display_name="Brian")
    store.set_password_hash("brian", "first")
    first = store.get_user("brian")["credentials_changed_at"]
    store.set_password_hash("brian", "second")
    assert store.get_user("brian")["credentials_changed_at"] != first


def test_timestamps_are_a_fixed_width_so_they_sort_as_text() -> None:
    # That comparison is a string comparison, so two widths would sort wrongly.
    # datetime.isoformat() drops the microseconds when they are zero, which is a
    # one-in-a-million event the test above cannot rely on hitting.
    stamp = _now()
    assert stamp.count(".") == 1
    assert len(stamp.split(".")[1]) == len("123456+00:00")


def test_set_password_hash_arms_and_clears_must_change(tmp_path) -> None:
    store = _store(tmp_path)
    store.create_user("brian", email=_EMAIL, display_name="Brian", password_hash="temp", must_change_password=True)
    store.set_password_hash("brian", "chosen", must_change_password=False)
    row = store.get_user("brian")
    assert row["password_hash"] == "chosen" and row["must_change_password"] == 0


def test_set_password_hash_on_unknown_user_raises(tmp_path) -> None:
    with pytest.raises(UnknownUserError):
        _store(tmp_path).set_password_hash("nope", "a-hash")


def test_record_login_stamps_last_login_at(tmp_path) -> None:
    store = _store(tmp_path)
    store.create_user("brian", email=_EMAIL, display_name="Brian")
    assert store.get_user("brian")["last_login_at"] is None
    store.record_login("brian")
    assert store.get_user("brian")["last_login_at"] is not None


def test_record_login_on_unknown_user_raises(tmp_path) -> None:
    with pytest.raises(UnknownUserError):
        _store(tmp_path).record_login("nope")


# --------------------------------------------------------- block and delete


def test_block_user_sets_blocked_at_and_stamps_credentials(tmp_path) -> None:
    store = _store(tmp_path)
    store.create_user("brian", email=_EMAIL, display_name="Brian", password_hash="a-hash")
    store.block_user("brian")
    row = store.get_user("brian")
    assert row["blocked_at"] is not None and row["credentials_changed_at"] is not None


def test_unblock_clears_blocked_at(tmp_path) -> None:
    store = _store(tmp_path)
    store.create_user("brian", email=_EMAIL, display_name="Brian")
    store.block_user("brian")
    store.unblock_user("brian")
    assert store.get_user("brian")["blocked_at"] is None


def test_soft_delete_keeps_app_state_and_oauth_links(tmp_path) -> None:
    store = _store(tmp_path)
    store.create_user(_USERNAME, email=_EMAIL, display_name="Abby")
    store.set_app_state(_USERNAME, {"edit_mode": "raw"})
    store.link_provider_account(_USERNAME, _PROVIDER, _ACCOUNT_ID, token=_REFRESH_TOKEN)
    store.soft_delete_user(_USERNAME)
    row = store.get_user(_USERNAME)
    assert row is not None and row["deleted_at"] is not None
    assert store.get_app_state(_USERNAME) is not None
    assert store.get_provider_account(_PROVIDER, _ACCOUNT_ID) is not None


def test_soft_delete_stamps_credentials_changed_at(tmp_path) -> None:
    store = _store(tmp_path)
    store.create_user("brian", email=_EMAIL, display_name="Brian")
    store.soft_delete_user("brian")
    assert store.get_user("brian")["credentials_changed_at"] is not None


def test_soft_deleted_username_stays_taken(tmp_path) -> None:
    store = _store(tmp_path)
    store.create_user("brian", email=_EMAIL, display_name="Brian")
    store.soft_delete_user("brian")
    with pytest.raises(UsernameTakenError):
        store.create_user("brian", email="other@example.com", display_name="Brian")


def test_block_and_delete_reject_an_unknown_user(tmp_path) -> None:
    store = _store(tmp_path)
    with pytest.raises(UnknownUserError):
        store.block_user("nope")
    with pytest.raises(UnknownUserError):
        store.unblock_user("nope")
    with pytest.raises(UnknownUserError):
        store.soft_delete_user("nope")


# ---------------------------------------------------------------- listing


def test_list_users_excludes_the_hash_and_the_internal_id(tmp_path) -> None:
    store = _store(tmp_path)
    store.create_user("brian", email=_EMAIL, display_name="Brian", password_hash="a-hash")
    (listed,) = store.list_users()
    assert "password_hash" not in listed
    assert "id" not in listed
    assert listed["username"] == "brian"


def test_list_users_reports_every_account_including_blocked_and_deleted(tmp_path) -> None:
    store = _store(tmp_path)
    store.create_user("brian", email=_EMAIL, display_name="Brian")
    store.create_user("alex", email="alex@example.com", display_name="Alex")
    store.create_user("carol", email="carol@example.com", display_name="Carol")
    store.block_user("alex")
    store.soft_delete_user("carol")
    listed = {row["username"]: row for row in store.list_users()}
    assert set(listed) == {"brian", "alex", "carol"}
    assert listed["brian"]["blocked_at"] is None
    assert listed["alex"]["blocked_at"] is not None
    assert listed["carol"]["deleted_at"] is not None
