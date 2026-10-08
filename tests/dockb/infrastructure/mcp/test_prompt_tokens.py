"""Tests for PromptTokenIssuer — mint and verify over an in-memory live-token map."""

from __future__ import annotations

import logging

from dockb.infrastructure.mcp import prompt_tokens
from dockb.infrastructure.mcp.prompt_tokens import PromptTokenIssuer

_TTL_ENV_VAR = "DOCKB_MCP_TOKEN_TTL_SECONDS"


def _issuer(ttl: float = 300.0) -> PromptTokenIssuer:
    return PromptTokenIssuer(ttl_seconds=ttl)


def _parts(token: str) -> tuple[str, str, str]:
    expiry, prompt_id, mac = token.split(".", 2)
    return expiry, prompt_id, mac


def test_token_has_three_dot_separated_fields() -> None:
    token = _issuer().mint("p1")
    expiry, prompt_id, mac = _parts(token)
    assert float(expiry) > 0
    assert "." not in expiry
    assert prompt_id == "p1"
    assert len(mac) == 64
    assert int(mac, 16) >= 0


def test_verify_returns_the_callers_prompt_id() -> None:
    issuer = _issuer()
    assert issuer.verify(issuer.mint("request-42")) == "request-42"


def test_prompt_id_may_contain_dots() -> None:
    issuer = _issuer()
    assert issuer.verify(issuer.mint("req.4.2")) == "req.4.2"


def test_tampered_mac_is_rejected() -> None:
    issuer = _issuer()
    expiry, prompt_id, mac = _parts(issuer.mint("p1"))
    forged = f"{expiry}.{prompt_id}.{mac[:-1]}{'0' if mac[-1] != '0' else '1'}"
    assert issuer.verify(forged) is None


def test_tampered_expiry_is_rejected() -> None:
    issuer = _issuer()
    expiry, prompt_id, mac = _parts(issuer.mint("p1"))
    extended = str(int(expiry) + 1_000_000)
    assert issuer.verify(f"{extended}.{prompt_id}.{mac}") is None


def test_tampered_prompt_id_is_rejected() -> None:
    issuer = _issuer()
    expiry, _, mac = _parts(issuer.mint("p1"))
    assert issuer.verify(f"{expiry}.p2.{mac}") is None


def test_token_from_a_dead_entry_is_rejected(monkeypatch) -> None:
    clock = {"now": 1_000_000.0}
    monkeypatch.setattr(prompt_tokens.time, "time", lambda: clock["now"])
    issuer = _issuer(ttl=60.0)
    token = issuer.mint("p1")
    clock["now"] += 61.0
    assert issuer.verify(token) is None


def test_token_with_no_live_entry_is_rejected() -> None:
    issuer = _issuer()
    foreign = _parts(_issuer().mint("p1"))
    assert issuer.verify(".".join(foreign)) is None


def test_malformed_tokens_are_rejected() -> None:
    issuer = _issuer()
    for token in ("", "no-dots", "1.2", "1.2.3.4", "not-a-number.p1.abcd"):
        assert issuer.verify(token) is None


def test_mint_prunes_expired_entries(monkeypatch) -> None:
    clock = {"now": 1_000_000.0}
    monkeypatch.setattr(prompt_tokens.time, "time", lambda: clock["now"])
    issuer = _issuer(ttl=60.0)
    issuer.mint("old")
    clock["now"] += 61.0
    issuer.mint("new")
    assert len(issuer._entries) == 1


def test_concurrent_prompts_both_verify(monkeypatch) -> None:
    clock = {"now": 1_000_000.0}
    monkeypatch.setattr(prompt_tokens.time, "time", lambda: clock["now"])
    issuer = _issuer(ttl=60.0)
    first = issuer.mint("a")
    clock["now"] += 30.0
    second = issuer.mint("b")
    assert issuer.verify(first) == "a"
    assert issuer.verify(second) == "b"


def test_ttl_defaults_to_300_from_the_environment(monkeypatch) -> None:
    monkeypatch.delenv(_TTL_ENV_VAR, raising=False)
    assert PromptTokenIssuer().ttl_seconds == 300.0
    monkeypatch.setenv(_TTL_ENV_VAR, "90")
    assert PromptTokenIssuer().ttl_seconds == 90.0


def test_token_expiry_is_now_plus_the_ttl(monkeypatch) -> None:
    clock = {"now": 1_000_000.0}
    monkeypatch.setattr(prompt_tokens.time, "time", lambda: clock["now"])
    expiry, _, _ = _parts(_issuer(ttl=60.0).mint("p1"))
    assert int(expiry) == 1_000_060_000_000


def test_verify_logs_the_prompt_identity_on_accept(caplog) -> None:
    issuer = _issuer()
    token = issuer.mint("p1")
    with caplog.at_level(logging.INFO, logger=prompt_tokens.__name__):
        issuer.verify(token)
    assert any("p1" in record.getMessage() for record in caplog.records)


def test_verify_logs_the_prompt_identity_and_reason_on_reject(caplog) -> None:
    issuer = _issuer()
    expiry, prompt_id, mac = _parts(issuer.mint("p1"))
    forged = f"{expiry}.{prompt_id}.{mac[:-1]}{'0' if mac[-1] != '0' else '1'}"
    with caplog.at_level(logging.INFO, logger=prompt_tokens.__name__):
        issuer.verify(forged)
    messages = [record.getMessage() for record in caplog.records]
    assert any("p1" in message and "reject" in message for message in messages)


def test_logged_prompt_id_cannot_forge_a_log_line(caplog) -> None:
    issuer = _issuer()
    expiry, prompt_id, mac = _parts(issuer.mint("p1"))
    forged = f"{expiry}.{prompt_id}.{mac[:-1]}{'0' if mac[-1] != '0' else '1'}"
    forged = forged.replace("p1", "p1\nforged: accepted")
    with caplog.at_level(logging.INFO, logger=prompt_tokens.__name__):
        issuer.verify(forged)
    assert len(caplog.records) == 1
    assert "\n" not in caplog.records[0].getMessage()


def test_verify_uses_a_constant_time_compare(monkeypatch) -> None:
    calls: list[tuple[bytes, bytes]] = []
    real_compare = prompt_tokens.hmac.compare_digest

    def spy(left: bytes, right: bytes) -> bool:
        calls.append((left, right))
        return real_compare(left, right)

    monkeypatch.setattr(prompt_tokens.hmac, "compare_digest", spy)
    issuer = _issuer()
    issuer.verify(issuer.mint("p1"))
    assert len(calls) == 1
