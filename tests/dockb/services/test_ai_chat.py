"""Tests for the AI chat service."""

from __future__ import annotations

from typing import Any

import pytest

from dockb.services.ai_chat import (
    _DEFAULT_MODEL,
    _MODEL_ENV_VAR,
    AiChatService,
    MissingApiKeyError,
)


class TestAiChatService:
    """complete() sends the prompt and returns the model's reply."""

    def test_prompt_passes_to_the_model_and_reply_comes_back(self) -> None:
        seen: list[str] = []

        def complete(prompt: str) -> str:
            seen.append(prompt)
            return "the reply"

        assert AiChatService(complete=complete).complete("what about chapter 2?") == "the reply"
        assert seen == ["what about chapter 2?"]

    def _post_capture(self, monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
        calls: list[dict[str, Any]] = []

        def post(url: str, **kwargs: Any) -> Any:
            calls.append({"url": url, **kwargs})
            return _fake_response()

        monkeypatch.setattr("dockb.services.ai_chat.httpx2.post", post)
        return calls

    def test_model_defaults_to_gpt_4o_mini(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv(_MODEL_ENV_VAR, raising=False)
        monkeypatch.setenv("OPENAI_API_KEY", "test-key")
        calls = self._post_capture(monkeypatch)
        AiChatService().complete("hi")
        assert calls[0]["json"]["model"] == _DEFAULT_MODEL

    def test_model_comes_from_the_environment(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv(_MODEL_ENV_VAR, "gpt-4.1-mini")
        monkeypatch.setenv("OPENAI_API_KEY", "test-key")
        calls = self._post_capture(monkeypatch)
        AiChatService().complete("hi")
        assert calls[0]["json"]["model"] == "gpt-4.1-mini"

    def test_the_call_is_one_user_message_with_the_raw_prompt(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("OPENAI_API_KEY", "test-key")
        calls = self._post_capture(monkeypatch)
        AiChatService().complete("  the prompt  ")
        assert calls[0]["url"] == "https://api.openai.com/v1/chat/completions"
        assert calls[0]["json"]["messages"] == [{"role": "user", "content": "  the prompt  "}]

    def test_a_whitespace_key_refuses_the_call(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("OPENAI_API_KEY", "   ")
        with pytest.raises(MissingApiKeyError):
            AiChatService().complete("hi")


def _fake_response() -> Any:
    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, Any]:
            return {"choices": [{"message": {"content": "reply text"}}]}

    return FakeResponse()
