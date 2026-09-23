"""Tests for PendingLoginStore — in-flight login state with TTL."""

from __future__ import annotations

from dockb.infrastructure.oauth.pending_login import PendingLoginStore

_SECRET_STORE = object()


def _store(ttl: float = 600.0) -> PendingLoginStore:
    return PendingLoginStore(ttl_seconds=ttl)


def test_issue_returns_distinct_state_verifier_pairs() -> None:
    store = _store()
    first = store.issue("google")
    second = store.issue("google")
    assert first != second
    assert first[0] != second[0]
    assert first[1] != second[1]
    assert all(part for part in first)


def test_consume_returns_matching_pending_login() -> None:
    store = _store()
    state, verifier = store.issue("github")
    pending = store.consume(state)
    assert pending is not None
    assert pending.provider == "github"
    assert pending.code_verifier == verifier


def test_consume_unknown_state_returns_none() -> None:
    assert _store().consume("forged-state") is None


def test_consume_removes_the_entry() -> None:
    store = _store()
    state, _ = store.issue("google")
    assert store.consume(state) is not None
    assert store.consume(state) is None


def test_consume_after_ttl_returns_none() -> None:
    store = _store(ttl=0.0)
    state, _ = store.issue("google")
    assert store.consume(state) is None


def test_issue_prunes_stale_entries(monkeypatch) -> None:
    clock = {"now": 0.0}
    monkeypatch.setattr("time.monotonic", lambda: clock["now"])
    store = _store(ttl=10.0)
    stale_state, _ = store.issue("google")
    clock["now"] = 20.0
    fresh_state, verifier = store.issue("github")
    assert store.consume(stale_state) is None
    pending = store.consume(fresh_state)
    assert pending is not None
    assert pending.code_verifier == verifier
