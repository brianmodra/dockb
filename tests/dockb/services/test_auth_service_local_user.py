"""Tests for the local-mode identity being created once rather than per request."""

from __future__ import annotations

from dockb.infrastructure.accounts.store import AccountStore
from dockb.infrastructure.oauth.pending_login import PendingLoginStore
from dockb.infrastructure.session.session_cookie import SessionSigner
from dockb.infrastructure.session.session_manager import SessionManager
from dockb.services.auth_service import AuthService


class _CountingAccountStore(AccountStore):
    """An AccountStore that records every local-user lookup."""

    def __init__(self, base_dir, secret: str) -> None:
        super().__init__(base_dir=base_dir, secret=secret)
        self.local_lookups: list[str] = []

    def get_or_create_local_user(self, username: str) -> str:
        self.local_lookups.append(username)
        return super().get_or_create_local_user(username)


class TestEnsureLocalUser:
    def _service(self, tmp_path) -> tuple[AuthService, _CountingAccountStore]:
        store = _CountingAccountStore(base_dir=tmp_path, secret="secret")
        service = AuthService({}, PendingLoginStore(), store, SessionManager(), SessionSigner("secret", ttl_hours=2))
        return service, store

    def test_creates_the_row_once_for_repeated_requests(self, tmp_path):
        """Every gated request passes through here, so it must not write each time."""
        service, store = self._service(tmp_path)
        for _ in range(5):
            assert service.ensure_local_user("abby") == "abby"
        assert store.local_lookups == ["abby"]

    def test_still_creates_a_missing_row(self, tmp_path):
        service, _ = self._service(tmp_path)
        service.ensure_local_user("abby")
        assert service.get_user("abby") is not None

    def test_recreates_for_a_different_username(self, tmp_path):
        """The memo is keyed on the username, so a changed identity is not skipped."""
        service, store = self._service(tmp_path)
        service.ensure_local_user("abby")
        service.ensure_local_user("robin")
        assert store.local_lookups == ["abby", "robin"]
