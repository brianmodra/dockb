"""Tests for the ``python -m dockb.cli.users`` admin CLI.

Driven through ``main(argv)`` rather than by calling the handlers, because the
things most likely to be wrong here are the argument parsing, the exit codes and
what lands on stdout or stderr — a password on the wrong stream, or an error that
exits 0. Each test also reads back the store, because "the command said it worked"
is not the same claim as "the account is in the state it described".

See ``README_auth.md`` §7.
"""

from __future__ import annotations

from contextlib import nullcontext
from dataclasses import dataclass, field, replace
from unittest.mock import MagicMock

import pytest

from dockb.cli import users as cli
from dockb.exceptions import DocumentFormatError, DocumentNotFoundError, DuplicateTitleError
from dockb.infrastructure.accounts.store import AccountStore
from dockb.infrastructure.document_store.factory import DocumentStoreFactory
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

    @pytest.mark.usefixtures("store")
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


@dataclass
class FakeAssignment:
    """What the assignment service reports, without touching the graph or the disk."""

    document_id: str
    title: str
    account_id: str = "acct-abby"
    tree_moved: bool = True
    already_owned: bool = False


@dataclass
class _ServiceCalls:
    """Everything the stand-in service was handed or asked to do, for a test to read."""

    assigned: list[tuple[str, str]] = field(default_factory=list)
    refuse_with: Exception | None = None
    refuse_ids: set[str] = field(default_factory=set)
    result: FakeAssignment = field(default_factory=lambda: FakeAssignment("d-1", "Faith"))
    store_factory: DocumentStoreFactory | None = None


@dataclass
class _SessionCalls:
    """Sessions opened and closed, and the settings they were opened with.

    A refusal that happens before the session is opened leaves this at zero, which is how
    "it named the missing setting without reaching the graph" is asserted.
    """

    opened: int = 0
    closed: int = 0
    settings: tuple[str, str, str] | None = None


class FakeService:  # pylint: disable=too-few-public-methods
    """Records what it was asked to assign, and refuses what a test told it to refuse.

    The service's own behaviour — the tree move, the refusals — is tested where it lives.
    What is under test here is the wiring: which account id the username resolved to,
    which document ids were passed on, what is printed, and what the exit code is.
    """

    def __init__(self, _document_repo, store_factory, calls: _ServiceCalls) -> None:
        self._calls = calls
        self._calls.store_factory = store_factory

    def assign(self, document_id: str, account_id: str) -> FakeAssignment:
        self._calls.assigned.append((document_id, account_id))
        if self._calls.refuse_with is not None:
            raise self._calls.refuse_with
        if document_id in self._calls.refuse_ids:
            raise DuplicateTitleError("'Faith' is already held by this account as d-9")
        result = self._calls.result
        if document_id != result.document_id:
            return replace(result, document_id=document_id)
        return result


class TestAssign:
    """``assign`` is the only command here that reaches the graph, so it is the only one
    whose refusals are mostly about documents. The account refusals are the same shape as
    every other command's: one ``error:`` line and a nonzero exit."""

    @pytest.fixture(autouse=True)
    def _neo4j(self, monkeypatch):
        monkeypatch.setenv("NEO4J_URL", "bolt://test:7687")
        monkeypatch.setenv("NEO4J_USER", "neo4j")
        monkeypatch.setenv("NEO4J_PASSWORD", "secret")

    @pytest.fixture()
    def service(self, monkeypatch) -> _ServiceCalls:
        calls = _ServiceCalls()
        monkeypatch.setattr(cli, "DocumentAssignmentService", lambda repo, factory: FakeService(repo, factory, calls))
        return calls

    @pytest.fixture()
    def unowned(self, monkeypatch) -> MagicMock:
        """The documents ``--all-to`` would move, as the repository reports them."""
        repo = MagicMock()
        repo.list_unowned.return_value = [{"id": "d-1", "title": "Faith"}, {"id": "d-2", "title": "Other"}]
        monkeypatch.setattr(cli, "DocumentRepository", lambda session: repo)
        return repo

    @pytest.fixture()
    def sessions(self, monkeypatch) -> _SessionCalls:
        """Count the sessions the command opened, so a refusal before them is visible."""
        calls = _SessionCalls()

        def _session():
            calls.opened += 1
            return nullcontext(MagicMock())

        def _close():
            calls.closed += 1

        def _factory(uri, user, password):
            calls.settings = (uri, user, password)
            return factory

        factory = MagicMock()
        factory.session.side_effect = _session
        factory.close.side_effect = _close
        monkeypatch.setattr(cli, "SessionFactory", _factory)
        return calls

    @pytest.fixture()
    def abby(self):
        _run(["create", "--username", "abby", "--email", "abby@example.com"])

    @pytest.mark.usefixtures("abby", "sessions")
    def test_it_gives_the_document_to_the_named_account(self, service, capsys, store):
        account_id = store.get_user("abby")["id"]

        assert _run(["assign", "d-1", "abby"]) == 0

        assert service.assigned == [("d-1", account_id)]
        assert "assigned d-1 (Faith)" in capsys.readouterr().out

    @pytest.mark.usefixtures("abby", "service")
    def test_it_reports_whether_the_tree_came_with_it(self, capsys):
        _run(["assign", "d-1", "abby"])
        assert "with its markdown tree" in capsys.readouterr().out

    @pytest.mark.usefixtures("abby")
    def test_it_says_so_when_the_document_had_no_tree_on_disk(self, service, capsys):
        service.result = FakeAssignment("d-1", "Faith", tree_moved=False)

        assert _run(["assign", "d-1", "abby"]) == 0

        assert "no markdown tree on disk" in capsys.readouterr().out

    @pytest.mark.usefixtures("abby")
    def test_it_says_so_when_the_account_already_held_it(self, service, capsys):
        service.result = FakeAssignment("d-1", "Faith", already_owned=True)

        assert _run(["assign", "d-1", "abby"]) == 0

        assert "already belongs" in capsys.readouterr().out

    @pytest.mark.usefixtures("abby")
    def test_it_reads_the_tree_from_the_servers_base_directory(self, service, tmp_path):
        _run(["assign", "d-1", "abby"])
        assert service.store_factory.for_account("acct-1").account_dir() == tmp_path / "acct-1"

    @pytest.mark.usefixtures("abby", "service")
    def test_it_closes_the_driver_it_opened(self, sessions):
        assert _run(["assign", "d-1", "abby"]) == 0

        assert (sessions.opened, sessions.closed) == (1, 1)

    @pytest.mark.usefixtures("abby", "service")
    def test_it_opens_the_graph_with_the_configured_settings(self, sessions):
        assert _run(["assign", "d-1", "abby"]) == 0

        assert sessions.settings == ("bolt://test:7687", "neo4j", "secret")

    def test_it_refuses_an_unknown_user_before_reaching_the_graph(self, service, sessions, capsys):
        assert _run(["assign", "d-1", "nobody"]) == 1
        assert sessions.opened == 0
        assert service.assigned == []

        assert "unknown user" in capsys.readouterr().err

    @pytest.mark.usefixtures("abby")
    def test_it_refuses_a_deleted_account(self, sessions, capsys):
        """A soft-deleted account cannot sign in, so this would hide the manuscript again."""
        _run(["delete", "abby", "--yes"])
        capsys.readouterr()

        assert _run(["assign", "d-1", "abby"]) == 1

        assert "undelete" in capsys.readouterr().err
        assert sessions.opened == 0

    @pytest.mark.usefixtures("abby")
    def test_a_blocked_account_is_still_a_destination(self, service, sessions):
        _run(["block", "abby"])

        assert _run(["assign", "d-1", "abby"]) == 0

        assert sessions.opened == 1
        assert service.assigned != []

    def test_it_needs_a_username(self, capsys):
        """A malformed command line, so it exits like argparse's usage errors."""
        assert _run(["assign"]) == 2
        assert "username" in capsys.readouterr().err

    @pytest.mark.usefixtures("abby", "service")
    def test_all_to_takes_no_document_id(self, capsys):
        """A stray positional is refused rather than read and ignored.

        ``--all-to abby d-1`` would put ``d-1`` in the document-id slot, which names
        nothing the command acts on — a whole library moved on a command line whose
        operator also named one document is exactly the confusion worth refusing. The
        two are mutually exclusive arguments, so argparse is what catches it.
        """
        assert _run(["assign", "--all-to", "abby", "d-1", "--yes"]) == 2

        error = capsys.readouterr().err
        assert "not allowed with argument --all-to" in error

    @pytest.mark.usefixtures("abby")
    def test_it_reports_a_title_the_document_cannot_be_stored_under(self, service, capsys):
        service.refuse_with = DocumentFormatError("document d-1 has a title that cannot be stored: '' is not a valid title")

        assert _run(["assign", "d-1", "abby"]) == 1

        assert "d-1" in capsys.readouterr().err

    @pytest.mark.usefixtures("abby")
    def test_without_the_graph_settings_it_names_them(self, sessions, capsys, monkeypatch):
        """Reported before anything is opened, the way the other two graph commands do.

        ``load_dotenv`` is neutralized rather than the variable unset: the command loads
        a ``.env`` file itself, so deleting the variable in the test would only let the
        developer's own file put it back.
        """
        monkeypatch.setattr(cli, "load_dotenv", lambda *a, **k: None)
        monkeypatch.delenv("NEO4J_URL")

        assert _run(["assign", "d-1", "abby"]) == 1

        assert "NEO4J_URL" in capsys.readouterr().err
        assert sessions.opened == 0

    @pytest.mark.usefixtures("abby")
    def test_it_reports_a_document_the_graph_does_not_have(self, service, capsys):
        service.refuse_with = DocumentNotFoundError("d-1")

        assert _run(["assign", "d-1", "abby"]) == 1

        assert "d-1" in capsys.readouterr().err

    @pytest.mark.usefixtures("abby")
    def test_it_reports_a_title_the_account_already_holds(self, service, capsys):
        service.refuse_with = DuplicateTitleError("'Faith' is already held by this account as d-9")

        assert _run(["assign", "d-1", "abby"]) == 1

        assert "d-9" in capsys.readouterr().err


class TestAssignAll:
    """``--all-to`` moves a whole library at once, so it is the one command here that is
    asked to confirm first and allowed to report a partly successful run."""

    @pytest.fixture(autouse=True)
    def _neo4j(self, monkeypatch):
        monkeypatch.setenv("NEO4J_URL", "bolt://test:7687")
        monkeypatch.setenv("NEO4J_USER", "neo4j")
        monkeypatch.setenv("NEO4J_PASSWORD", "secret")

    @pytest.fixture()
    def service(self, monkeypatch) -> _ServiceCalls:
        calls = _ServiceCalls()
        monkeypatch.setattr(cli, "DocumentAssignmentService", lambda repo, factory: FakeService(repo, factory, calls))
        return calls

    @pytest.fixture()
    def unowned(self, monkeypatch) -> MagicMock:
        repo = MagicMock()
        repo.list_unowned.return_value = [{"id": "d-1", "title": "Faith"}, {"id": "d-2", "title": "Other"}]
        monkeypatch.setattr(cli, "DocumentRepository", lambda session: repo)
        return repo

    @pytest.fixture()
    def sessions(self, monkeypatch) -> _SessionCalls:
        calls = _SessionCalls()

        def _session():
            calls.opened += 1
            return nullcontext(MagicMock())

        def _close():
            calls.closed += 1

        def _factory(uri, user, password):
            calls.settings = (uri, user, password)
            return factory

        factory = MagicMock()
        factory.session.side_effect = _session
        factory.close.side_effect = _close
        monkeypatch.setattr(cli, "SessionFactory", _factory)
        return calls

    @pytest.fixture()
    def abby(self):
        _run(["create", "--username", "abby", "--email", "abby@example.com"])

    @pytest.mark.usefixtures("abby", "sessions", "unowned")
    def test_it_refuses_without_yes_and_moves_nothing(self, service, capsys):
        assert _run(["assign", "--all-to", "abby"]) == 1

        assert service.assigned == []
        error = capsys.readouterr().err
        assert "--yes" in error
        assert "2 document(s)" in error

    @pytest.mark.usefixtures("unowned", "sessions", "abby")
    def test_it_gives_every_unowned_document_to_the_named_account(self, service, capsys, store):
        account_id = store.get_user("abby")["id"]

        assert _run(["assign", "--all-to", "abby", "--yes"]) == 0

        assert service.assigned == [("d-1", account_id), ("d-2", account_id)]
        out = capsys.readouterr().out
        assert "assigned d-1" in out
        assert "assigned d-2" in out

    @pytest.mark.usefixtures("unowned", "sessions", "abby")
    def test_one_refusal_does_not_strand_the_rest(self, service, capsys):
        """A single title clash is not a reason to leave a whole library unassigned."""
        service.refuse_ids = {"d-1"}

        assert _run(["assign", "--all-to", "abby", "--yes"]) == 1

        assert [document_id for document_id, _ in service.assigned] == ["d-1", "d-2"]
        captured = capsys.readouterr()
        assert "assigned d-2" in captured.out
        assert "1 of 2 document(s) were not assigned" in captured.err

    @pytest.mark.usefixtures("abby", "sessions")
    def test_it_says_when_there_is_nothing_to_assign(self, service, capsys, monkeypatch):
        monkeypatch.setattr(cli, "DocumentRepository", lambda session: MagicMock(list_unowned=MagicMock(return_value=[])))

        assert _run(["assign", "--all-to", "abby", "--yes"]) == 0

        assert "every document already belongs to an account" in capsys.readouterr().out
        assert service.assigned == []

    @pytest.mark.usefixtures("sessions")
    def test_it_checks_the_destination_before_reaching_the_graph(self, service, capsys):
        assert _run(["assign", "--all-to", "nobody", "--yes"]) == 1

        assert "unknown user" in capsys.readouterr().err
        assert service.assigned == []
