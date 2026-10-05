"""Tests for the ``python -m dockb.cli.users`` admin CLI.

Driven through ``main(argv)`` rather than by calling the handlers, because the
things most likely to be wrong here are the argument parsing, the exit codes and
what lands on stdout or stderr — a password on the wrong stream, or an error that
exits 0. Each test also reads back the store, because "the command said it worked"
is not the same claim as "the account is in the state it described".

See ``README_auth.md`` §7.
"""

from __future__ import annotations

import pytest

from dockb.cli import users as cli
from dockb.infrastructure.accounts.store import AccountStore
from dockb.passwords import pepper_from, verify_password

_SECRET = "a-server-secret"


@pytest.fixture(autouse=True)
def _configured(tmp_path, monkeypatch):
    """Give every test a working configuration, so a failure is the command's doing.

    The CLI resolves both of these itself, exactly as the server does, so pinning them
    here is what keeps a test from reaching the developer's own account database.
    ``TestMissingConfiguration`` deliberately unpins the secret to exercise the refusal.
    """
    monkeypatch.setenv("DOCKB_SECRET_KEY", _SECRET)
    monkeypatch.setattr(cli, "resolve_document_base_dir", lambda *a, **k: tmp_path)


@pytest.fixture()
def store(tmp_path) -> AccountStore:
    """A second store over the same file, for a test to assert through.

    Deliberately not the object the command used: the CLI builds its own, so reading
    back through a different one proves the command wrote to the database rather than
    to something it happened to be holding.
    """
    return AccountStore(base_dir=tmp_path, secret=_SECRET)


def _run(argv) -> int:
    """Run the CLI and return its exit code."""
    return cli.main(argv)


class TestMissingConfiguration:

    def test_without_a_secret_it_says_so_and_exits_nonzero(self, capsys, monkeypatch):
        monkeypatch.delenv("DOCKB_SECRET_KEY", raising=False)
        assert cli.main(["list"]) == 1
        assert "DOCKB_SECRET_KEY" in capsys.readouterr().err

    def test_a_blank_secret_counts_as_missing(self, capsys, monkeypatch):
        """A whitespace secret is truthy, and would be a weak key for everything."""
        monkeypatch.setenv("DOCKB_SECRET_KEY", "   ")
        assert cli.main(["list"]) == 1
        assert "DOCKB_SECRET_KEY" in capsys.readouterr().err


class TestCreate:
    def test_it_creates_the_account(self, store):
        assert _run(["create", "--username", "abby", "--email", "abby@example.com"]) == 0
        assert store.get_user("abby")["email"] == "abby@example.com"

    def test_it_prints_a_temporary_password_exactly_once(self, store, capsys):
        _run(["create", "--username", "abby", "--email", "abby@example.com"])
        out = capsys.readouterr().out
        temporary = out.strip().splitlines()[-1].strip()
        assert temporary
        assert verify_password(pepper_from(_SECRET), temporary, store.get_credentials("abby")["password_hash"])

    def test_the_temporary_password_verifies_and_arms_the_change(self, store):
        _run(["create", "--username", "abby", "--email", "abby@example.com"])
        credentials = store.get_credentials("abby")
        assert credentials["must_change_password"] == 1

    def test_it_never_prints_the_hash(self, store, capsys):
        _run(["create", "--username", "abby", "--email", "abby@example.com"])
        assert store.get_credentials("abby")["password_hash"] not in capsys.readouterr().out

    def test_the_display_name_defaults_to_the_username(self, store):
        _run(["create", "--username", "abby", "--email", "abby@example.com"])
        assert store.get_user("abby")["display_name"] == "abby"

    def test_a_display_name_can_be_given(self, store):
        _run(["create", "--username", "abby", "--email", "abby@example.com", "--display-name", "Abby L."])
        assert store.get_user("abby")["display_name"] == "Abby L."

    def test_the_username_is_normalized(self, store, capsys):
        _run(["create", "--username", "  Abby  ", "--email", "abby@example.com"])
        assert store.get_user("abby") is not None
        assert "abby" in capsys.readouterr().out

    def test_a_username_that_differs_only_by_case_is_refused(self, store, capsys):
        """Otherwise one person ends up with two accounts and two sets of documents."""
        _run(["create", "--username", "abby", "--email", "abby@example.com"])
        capsys.readouterr()
        assert _run(["create", "--username", "ABBY", "--email", "other@example.com"]) == 1
        assert [u["username"] for u in store.list_users()] == ["abby"]
        assert capsys.readouterr().err.strip()

    def test_a_duplicate_email_is_refused_and_says_which(self, capsys):
        _run(["create", "--username", "abby", "--email", "abby@example.com"])
        capsys.readouterr()
        assert _run(["create", "--username", "brian", "--email", "abby@example.com"]) == 1
        assert "abby@example.com" in capsys.readouterr().err

    def test_an_email_is_required(self, capsys):
        """The column is nullable for provider rows, but an admin supplies one."""
        assert _run(["create", "--username", "abby"]) == 2
        assert "--email" in capsys.readouterr().err

    def test_a_username_is_required(self, capsys):
        assert _run(["create", "--email", "abby@example.com"]) == 2
        assert "--username" in capsys.readouterr().err

    def test_a_created_account_can_sign_in(self, store, capsys):
        """The whole point: a fresh install now has somebody who can get in."""
        _run(["create", "--username", "abby", "--email", "abby@example.com"])
        temporary = capsys.readouterr().out.strip().splitlines()[-1].strip()
        from dockb.infrastructure.oauth.pending_login import PendingLoginStore
        from dockb.infrastructure.session.session_cookie import SessionSigner
        from dockb.infrastructure.session.session_manager import SessionManager
        from dockb.services.auth_service import AuthService

        service = AuthService(
            {},
            PendingLoginStore(),
            store,
            SessionManager(),
            SessionSigner(_SECRET, ttl_hours=2),
            pepper=pepper_from(_SECRET),
        )
        assert service.login_with_password("abby", temporary, client_ip="10.0.0.1") == "abby"
        assert service.requires_password_change("abby") is True


class TestSetPassword:
    def test_it_issues_a_new_temporary_password(self, store, capsys):
        _run(["create", "--username", "abby", "--email", "abby@example.com"])
        first = capsys.readouterr().out.strip().splitlines()[-1].strip()
        assert _run(["set-password", "abby"]) == 0
        second = capsys.readouterr().out.strip().splitlines()[-1].strip()
        assert second != first
        assert verify_password(pepper_from(_SECRET), second, store.get_credentials("abby")["password_hash"])

    def test_the_old_password_no_longer_works(self, store, capsys):
        _run(["create", "--username", "abby", "--email", "abby@example.com"])
        first = capsys.readouterr().out.strip().splitlines()[-1].strip()
        _run(["set-password", "abby"])
        capsys.readouterr()
        assert verify_password(pepper_from(_SECRET), first, store.get_credentials("abby")["password_hash"]) is False

    def test_it_re_arms_the_must_change_flag(self, store):
        _run(["create", "--username", "abby", "--email", "abby@example.com"])
        from dockb.passwords import hash_password

        store.set_password_hash("abby", hash_password(pepper_from(_SECRET), "chosen-by-them"), must_change_password=False)
        _run(["set-password", "abby"])
        assert store.get_credentials("abby")["must_change_password"] == 1

    def test_it_stamps_the_credentials(self, store):
        """Which is what ends the live sessions a reset is meant to end.

        create leaves the stamp NULL, because a new account has no session to
        invalidate; the reset is what first puts one there.
        """
        _run(["create", "--username", "abby", "--email", "abby@example.com"])
        assert store.get_credentials("abby")["credentials_changed_at"] is None
        _run(["set-password", "abby"])
        assert store.get_credentials("abby")["credentials_changed_at"] is not None

    def test_an_unknown_username_is_an_error_not_a_crash(self, capsys):
        assert _run(["set-password", "nobody"]) == 1
        assert "nobody" in capsys.readouterr().err


class TestList:
    def test_it_lists_the_accounts(self, capsys):
        _run(["create", "--username", "abby", "--email", "abby@example.com"])
        _run(["create", "--username", "brian", "--email", "brian@example.com"])
        out = capsys.readouterr().out
        assert "abby" in out and "brian" in out

    def test_it_never_prints_a_hash_or_a_password(self, store, capsys):
        _run(["create", "--username", "abby", "--email", "abby@example.com"])
        temporary = capsys.readouterr().out.strip().splitlines()[-1].strip()
        password_hash = store.get_credentials("abby")["password_hash"]
        assert _run(["list"]) == 0
        out = capsys.readouterr().out
        assert out.strip(), "expected some output"
        assert password_hash not in out
        assert temporary not in out

    def test_it_reports_state(self, capsys):
        _run(["create", "--username", "abby", "--email", "abby@example.com"])
        _run(["block", "abby"])
        out = capsys.readouterr().out
        assert "abby" in out
        assert "blocked" in out

    def test_it_shows_a_deleted_account_rather_than_hiding_it(self, capsys):
        """A deleted account and one that never existed are different states."""
        _run(["create", "--username", "abby", "--email", "abby@example.com"])
        _run(["delete", "abby", "--yes"])
        out = capsys.readouterr().out
        assert "abby" in out
        assert "deleted" in out

    def test_it_says_so_when_there_are_none(self, capsys):
        assert _run(["list"]) == 0
        assert "no accounts" in capsys.readouterr().out.lower()


class TestBlock:
    def test_it_blocks_the_account(self, store):
        _run(["create", "--username", "abby", "--email", "abby@example.com"])
        assert _run(["block", "abby"]) == 0
        assert store.get_credentials("abby")["blocked_at"] is not None

    def test_blocking_stamps_the_credentials(self, store):
        """Which is what actually ends the live sessions."""
        _run(["create", "--username", "abby", "--email", "abby@example.com"])
        assert store.get_credentials("abby")["credentials_changed_at"] is None
        _run(["block", "abby"])
        assert store.get_credentials("abby")["credentials_changed_at"] is not None

    def test_it_takes_a_username_in_any_case(self):
        _run(["create", "--username", "abby", "--email", "abby@example.com"])
        assert _run(["block", "ABBY"]) == 0

    def test_an_unknown_username_is_an_error(self, capsys):
        assert _run(["block", "nobody"]) == 1
        assert "nobody" in capsys.readouterr().err

    def test_unblock_reverses_it(self, store):
        _run(["create", "--username", "abby", "--email", "abby@example.com"])
        _run(["block", "abby"])
        assert _run(["unblock", "abby"]) == 0
        assert store.get_credentials("abby")["blocked_at"] is None

    def test_unblocking_does_not_resurrect_the_sessions_the_block_ended(self, store):
        """Unblocking is not a credential change, so it must not hand one back."""
        _run(["create", "--username", "abby", "--email", "abby@example.com"])
        before = store.get_credentials("abby")["credentials_changed_at"]
        _run(["block", "abby"])
        _run(["unblock", "abby"])
        assert store.get_credentials("abby")["credentials_changed_at"] != before


class TestDelete:
    def test_it_soft_deletes(self, store):
        _run(["create", "--username", "abby", "--email", "abby@example.com"])
        assert _run(["delete", "abby", "--yes"]) == 0
        assert store.get_credentials("abby")["deleted_at"] is not None

    def test_it_refuses_without_yes_and_changes_nothing(self, store, capsys):
        _run(["create", "--username", "abby", "--email", "abby@example.com"])
        capsys.readouterr()
        assert _run(["delete", "abby"]) == 1
        assert store.get_credentials("abby")["deleted_at"] is None
        assert "--yes" in capsys.readouterr().err

    def test_the_account_row_survives(self, store):
        _run(["create", "--username", "abby", "--email", "abby@example.com"])
        _run(["delete", "abby", "--yes"])
        assert store.get_user("abby") is not None

    def test_the_username_stays_taken(self, capsys):
        """The row is still there, so the name is still somebody's."""
        _run(["create", "--username", "abby", "--email", "abby@example.com"])
        _run(["delete", "abby", "--yes"])
        capsys.readouterr()
        assert _run(["create", "--username", "abby", "--email", "new@example.com"]) == 1
        assert "taken" in capsys.readouterr().err.lower()

    def test_the_taken_username_is_reported_as_the_deleted_one(self, capsys):
        """So an admin can tell a deleted account from a typo'd new one."""
        _run(["create", "--username", "abby", "--email", "abby@example.com"])
        _run(["delete", "abby", "--yes"])
        capsys.readouterr()
        assert _run(["create", "--username", "abby", "--email", "new@example.com"]) == 1
        assert "deleted" in capsys.readouterr().err.lower()

    def test_undelete_restores_the_account(self, store):
        _run(["create", "--username", "abby", "--email", "abby@example.com"])
        _run(["delete", "abby", "--yes"])
        assert _run(["undelete", "abby"]) == 0
        assert store.get_credentials("abby")["deleted_at"] is None

    def test_undelete_leaves_the_credentials_alone(self, store, capsys):
        """It restores what was there rather than inventing a new state."""
        _run(["create", "--username", "abby", "--email", "abby@example.com"])
        temporary = capsys.readouterr().out.strip().splitlines()[-1].strip()
        password_hash = store.get_credentials("abby")["password_hash"]
        _run(["delete", "abby", "--yes"])
        _run(["undelete", "abby"])
        assert store.get_credentials("abby")["password_hash"] == password_hash
        assert verify_password(pepper_from(_SECRET), temporary, password_hash)

    def test_undelete_does_not_re_arm_the_must_change_flag(self, store):
        _run(["create", "--username", "abby", "--email", "abby@example.com"])
        from dockb.passwords import hash_password

        store.set_password_hash("abby", hash_password(pepper_from(_SECRET), "chosen-by-them"), must_change_password=False)
        _run(["delete", "abby", "--yes"])
        _run(["undelete", "abby"])
        assert store.get_credentials("abby")["must_change_password"] == 0

    def test_undelete_stamps_the_credentials(self, store):
        """So a session issued before the delete does not come back with it."""
        _run(["create", "--username", "abby", "--email", "abby@example.com"])
        before = store.get_credentials("abby")["credentials_changed_at"]
        _run(["delete", "abby", "--yes"])
        deleted_stamp = store.get_credentials("abby")["credentials_changed_at"]
        assert _run(["undelete", "abby"]) == 0
        assert store.get_credentials("abby")["credentials_changed_at"] > deleted_stamp
        assert store.get_credentials("abby")["credentials_changed_at"] != before


class TestParser:
    def test_an_unknown_command_exits_nonzero_with_the_usage(self, capsys):
        assert cli.main(["frobnicate"]) != 0
        captured = capsys.readouterr()
        assert "usage" in (captured.err + captured.out).lower()

    def test_no_command_exits_nonzero(self):
        assert cli.main([]) != 0

    def test_a_usage_error_is_distinct_from_a_refusal(self):
        """2 is a malformed command line; 1 is a command that ran and declined."""
        assert cli.main([]) == 2
        assert cli.main(["create", "--username", "abby"]) == 2
