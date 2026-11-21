"""Tests for password-recovery and two-factor state in AccountStore."""

from __future__ import annotations

import sqlite3

from dockb.infrastructure.accounts.store import (
    _SCHEMA_VERSION,
    AccountStore,
    TokenEncryptor,
)

_SECRET = "test-secret-key"
_USERNAME = "abby"
_EMAIL = "abby@example.com"
_FIRST = "2026-01-01T00:00:00.000000+00:00"
_EXPIRES = "2026-01-02T00:00:00.000000+00:00"
_AFTER = "2026-01-03T00:00:00.000000+00:00"

_V2_USERS = """
CREATE TABLE users (
    id                      TEXT PRIMARY KEY,
    username                TEXT NOT NULL UNIQUE,
    email                   TEXT,
    display_name            TEXT,
    avatar_url              TEXT,
    password_hash           TEXT,
    must_change_password    INTEGER NOT NULL DEFAULT 0,
    blocked_at              TEXT,
    last_login_at           TEXT,
    credentials_changed_at  TEXT,
    deleted_at              TEXT,
    created_at              TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""

_V3_APP_STATE = """
CREATE TABLE app_state (
    username           TEXT PRIMARY KEY,
    last_document_id   TEXT,
    panel_widths       TEXT,
    edit_mode          TEXT,
    updated_at         TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""


def _store(tmp_path) -> AccountStore:
    return AccountStore(base_dir=tmp_path, secret=_SECRET)


def _user_version(tmp_path) -> int:
    connection = sqlite3.connect(tmp_path / "dockb_app.db")
    try:
        return int(connection.execute("PRAGMA user_version").fetchone()[0])
    finally:
        connection.close()


def _has_table(tmp_path, name: str) -> bool:
    connection = sqlite3.connect(tmp_path / "dockb_app.db")
    try:
        return connection.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (name,)).fetchone() is not None
    finally:
        connection.close()


def _user_columns(tmp_path) -> set[str]:
    connection = sqlite3.connect(tmp_path / "dockb_app.db")
    try:
        return {row[1] for row in connection.execute("PRAGMA table_info(users)")}
    finally:
        connection.close()


def _v4_database(tmp_path) -> None:
    connection = sqlite3.connect(tmp_path / "dockb_app.db")
    try:
        connection.executescript(_V2_USERS)
        connection.execute(
            "INSERT INTO users (id, username, display_name) VALUES ('id-abby', 'abby', 'Abby')",
        )
        connection.executescript(_V3_APP_STATE)
        connection.execute("ALTER TABLE app_state ADD COLUMN proofreading_language TEXT")
        connection.execute("PRAGMA user_version = 4")
        connection.commit()
    finally:
        connection.close()


def test_fresh_database_has_the_two_factor_schema(tmp_path) -> None:
    _store(tmp_path).get_user("anyone")
    columns = _user_columns(tmp_path)
    assert {"two_factor_method", "totp_secret"} <= columns
    assert _has_table(tmp_path, "password_reset_tokens")
    assert _has_table(tmp_path, "login_challenges")
    assert _has_table(tmp_path, "email_otps")
    assert _user_version(tmp_path) == _SCHEMA_VERSION


def test_migration_from_v4_adds_two_factor_schema(tmp_path) -> None:
    _v4_database(tmp_path)
    store = _store(tmp_path)
    user = store.get_user("abby")
    assert user is not None
    assert user["display_name"] == "Abby"
    assert {"two_factor_method", "totp_secret"} <= _user_columns(tmp_path)
    assert _has_table(tmp_path, "password_reset_tokens")
    assert _has_table(tmp_path, "login_challenges")
    assert _has_table(tmp_path, "email_otps")
    assert _user_version(tmp_path) == _SCHEMA_VERSION


def test_two_factor_secret_round_trip_is_encrypted(tmp_path) -> None:
    store = _store(tmp_path)
    store.create_user(_USERNAME, email=_EMAIL, display_name="Abby")
    store.set_two_factor(_USERNAME, method="totp", totp_secret="JBSWY3DPEHPK3PXP")

    state = store.get_two_factor_state(_USERNAME)
    assert state is not None
    assert state["method"] == "totp"
    assert state["totp_secret"] == "JBSWY3DPEHPK3PXP"
    connection = sqlite3.connect(tmp_path / "dockb_app.db")
    try:
        ciphertext = connection.execute("SELECT totp_secret FROM users WHERE username = ?", (_USERNAME,)).fetchone()[0]
    finally:
        connection.close()
    assert isinstance(ciphertext, bytes)
    assert b"JBSWY3DPEHPK3PXP" not in ciphertext
    assert TokenEncryptor(_SECRET).try_decrypt(ciphertext) is None


def test_setting_email_two_factor_removes_the_totp_secret(tmp_path) -> None:
    store = _store(tmp_path)
    store.create_user(_USERNAME, email=_EMAIL, display_name="Abby")
    store.set_two_factor(_USERNAME, method="totp", totp_secret="JBSWY3DPEHPK3PXP")

    store.set_two_factor(_USERNAME, method="email")

    state = store.get_two_factor_state(_USERNAME)
    assert state is not None
    assert state["method"] == "email"
    assert state["totp_secret"] is None


def test_clear_two_factor_removes_pending_state_and_invalidates_sessions(tmp_path) -> None:
    store = _store(tmp_path)
    store.create_user(_USERNAME, email=_EMAIL, display_name="Abby")
    stamp = store.get_user(_USERNAME)["credentials_changed_at"]
    store.set_two_factor(_USERNAME, method="totp", totp_secret="JBSWY3DPEHPK3PXP")
    store.issue_password_reset(_USERNAME, token_hash="reset-hash", expires_at=_EXPIRES)
    store.issue_login_challenge(_USERNAME, token_hash="challenge-hash", method="email", expires_at=_EXPIRES)
    store.issue_email_otp(_USERNAME, code_hash="otp-hash", expires_at=_EXPIRES)

    store.clear_two_factor(_USERNAME)

    state = store.get_two_factor_state(_USERNAME)
    assert state is not None
    assert state["method"] is None
    assert state["totp_secret"] is None
    assert store.consume_password_reset("reset-hash", now=_FIRST) is None
    assert store.consume_login_challenge("challenge-hash", now=_FIRST) is None
    assert not store.verify_email_otp(_USERNAME, code_hash="otp-hash", now=_FIRST)
    assert store.get_user(_USERNAME)["credentials_changed_at"] != stamp


def test_password_reset_token_is_single_use(tmp_path) -> None:
    store = _store(tmp_path)
    store.create_user(_USERNAME, email=_EMAIL, display_name="Abby")
    store.issue_password_reset(_USERNAME, token_hash="reset-hash", expires_at=_EXPIRES)

    assert store.consume_password_reset("reset-hash", now=_FIRST) == _USERNAME
    assert store.consume_password_reset("reset-hash", now=_FIRST) is None


def test_password_reset_token_expires(tmp_path) -> None:
    store = _store(tmp_path)
    store.create_user(_USERNAME, email=_EMAIL, display_name="Abby")
    store.issue_password_reset(_USERNAME, token_hash="reset-hash", expires_at=_EXPIRES)

    assert store.consume_password_reset("reset-hash", now=_AFTER) is None


def test_login_challenge_is_single_use(tmp_path) -> None:
    store = _store(tmp_path)
    store.create_user(_USERNAME, email=_EMAIL, display_name="Abby")
    store.issue_login_challenge(_USERNAME, token_hash="challenge-hash", method="email", expires_at=_EXPIRES)

    assert store.consume_login_challenge("challenge-hash", now=_FIRST) == _USERNAME
    assert store.consume_login_challenge("challenge-hash", now=_FIRST) is None


def test_login_challenge_expires(tmp_path) -> None:
    store = _store(tmp_path)
    store.create_user(_USERNAME, email=_EMAIL, display_name="Abby")
    store.issue_login_challenge(_USERNAME, token_hash="challenge-hash", method="totp", expires_at=_EXPIRES)

    assert store.consume_login_challenge("challenge-hash", now=_AFTER) is None


def test_email_otp_is_single_use(tmp_path) -> None:
    store = _store(tmp_path)
    store.create_user(_USERNAME, email=_EMAIL, display_name="Abby")
    store.issue_email_otp(_USERNAME, code_hash="otp-hash", expires_at=_EXPIRES)

    assert store.verify_email_otp(_USERNAME, code_hash="otp-hash", now=_FIRST)
    assert not store.verify_email_otp(_USERNAME, code_hash="otp-hash", now=_FIRST)


def test_email_otp_rejects_a_wrong_code_without_consuming_it(tmp_path) -> None:
    store = _store(tmp_path)
    store.create_user(_USERNAME, email=_EMAIL, display_name="Abby")
    store.issue_email_otp(_USERNAME, code_hash="otp-hash", expires_at=_EXPIRES)

    assert not store.verify_email_otp(_USERNAME, code_hash="wrong-hash", now=_FIRST)
    assert store.verify_email_otp(_USERNAME, code_hash="otp-hash", now=_FIRST)


def test_email_otp_locks_after_five_wrong_codes(tmp_path) -> None:
    store = _store(tmp_path)
    store.create_user(_USERNAME, email=_EMAIL, display_name="Abby")
    store.issue_email_otp(_USERNAME, code_hash="otp-hash", expires_at=_EXPIRES)

    for _ in range(5):
        assert not store.verify_email_otp(_USERNAME, code_hash="wrong-hash", now=_FIRST)
    assert not store.verify_email_otp(_USERNAME, code_hash="otp-hash", now=_FIRST)


def test_email_otp_expires(tmp_path) -> None:
    store = _store(tmp_path)
    store.create_user(_USERNAME, email=_EMAIL, display_name="Abby")
    store.issue_email_otp(_USERNAME, code_hash="otp-hash", expires_at=_EXPIRES)

    assert not store.verify_email_otp(_USERNAME, code_hash="otp-hash", now=_AFTER)


def test_issuing_a_new_email_otp_resets_attempts(tmp_path) -> None:
    store = _store(tmp_path)
    store.create_user(_USERNAME, email=_EMAIL, display_name="Abby")
    store.issue_email_otp(_USERNAME, code_hash="old-hash", expires_at=_EXPIRES)
    for _ in range(4):
        assert not store.verify_email_otp(_USERNAME, code_hash="wrong-hash", now=_FIRST)

    store.issue_email_otp(_USERNAME, code_hash="new-hash", expires_at=_EXPIRES)
    assert not store.verify_email_otp(_USERNAME, code_hash="wrong-hash", now=_FIRST)
    assert store.verify_email_otp(_USERNAME, code_hash="new-hash", now=_FIRST)


def test_get_user_by_email_matches_case_insensitively(tmp_path) -> None:
    store = _store(tmp_path)
    store.create_user(_USERNAME, email=_EMAIL, display_name="Abby")

    user = store.get_user_by_email("  ABBY@EXAMPLE.COM  ")

    assert user is not None
    assert user["username"] == _USERNAME
    assert store.get_user_by_email("nobody@example.com") is None


def test_get_login_challenge_does_not_consume_it(tmp_path) -> None:
    store = _store(tmp_path)
    store.create_user(_USERNAME, email=_EMAIL, display_name="Abby")
    store.issue_login_challenge(_USERNAME, token_hash="challenge-hash", method="totp", expires_at=_EXPIRES)

    assert store.get_login_challenge("challenge-hash", now=_FIRST) == _USERNAME
    assert store.get_login_challenge("challenge-hash", now=_FIRST) == _USERNAME
    assert store.consume_login_challenge("challenge-hash", now=_FIRST) == _USERNAME
    assert store.get_login_challenge("challenge-hash", now=_FIRST) is None


def test_get_login_challenge_refuses_an_expired_challenge(tmp_path) -> None:
    store = _store(tmp_path)
    store.create_user(_USERNAME, email=_EMAIL, display_name="Abby")
    store.issue_login_challenge(_USERNAME, token_hash="challenge-hash", method="totp", expires_at=_EXPIRES)

    assert store.get_login_challenge("challenge-hash", now=_AFTER) is None
