"""Tests for POST /api/ai/chat."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from dockb.controllers.ai import chat, set_ai_service
from dockb.controllers.auth import get_owner
from dockb.services.ai_chat import MissingApiKeyError


def _make_app(overridden_owner: str | None = None) -> FastAPI:
    app = FastAPI()
    app.dependency_overrides[get_owner] = lambda: overridden_owner or "account-0"
    app.add_api_route("/api/ai/chat", chat, methods=["POST"])
    return app


class _StubService:  # pylint: disable=too-few-public-methods
    def __init__(self, reply: str = "the reply", error: Exception | None = None) -> None:
        self.reply = reply
        self.error = error
        self.calls: list[tuple[str, str]] = []

    def complete(self, prompt: str, account_id: str = "") -> str:
        self.calls.append((prompt, account_id))
        if self.error is not None:
            raise self.error
        return self.reply


class TestChatRoute:
    """POST /api/ai/chat sends the prompt and the account id, returns the reply."""

    def setup_method(self) -> None:
        self.service: _StubService | None = None
        self.client = TestClient(_make_app())

    def teardown_method(self) -> None:
        set_ai_service(None)
        self.client.app.dependency_overrides.pop(get_owner, None)

    def _wire(self, service: _StubService, owner: str | None = None) -> None:
        self.service = service
        set_ai_service(service)
        if owner is not None:
            self.client = TestClient(_make_app(owner))
            set_ai_service(service)

    def test_returns_the_model_reply(self) -> None:
        self._wire(_StubService("answer"))
        resp = self.client.post("/api/ai/chat", json={"prompt": "hello"})
        assert resp.status_code == 200
        assert resp.json() == {"reply": "answer"}
        assert self.service is not None and self.service.calls == [("hello", "account-0")]

    def test_without_a_service_answers_503(self) -> None:
        resp = self.client.post("/api/ai/chat", json={"prompt": "hello"})
        assert resp.status_code == 503

    def test_missing_api_key_answers_503(self) -> None:
        self._wire(_StubService(error=MissingApiKeyError("no key")))
        resp = self.client.post("/api/ai/chat", json={"prompt": "hello"})
        assert resp.status_code == 503

    def test_an_openai_failure_answers_502(self) -> None:
        self._wire(_StubService(error=RuntimeError("boom")))
        resp = self.client.post("/api/ai/chat", json={"prompt": "hello"})
        assert resp.status_code == 502

    def test_an_empty_prompt_is_rejected(self) -> None:
        self._wire(_StubService())
        resp = self.client.post("/api/ai/chat", json={"prompt": ""})
        assert resp.status_code == 422
        assert resp.json()["detail"][0]["loc"][-1] == "prompt"

    def test_the_prompt_is_sent_for_the_signed_in_account(self) -> None:
        self._wire(_StubService("answer"), owner="account-9")
        resp = self.client.post("/api/ai/chat", json={"prompt": "hello"})
        assert resp.status_code == 200
        assert self.service is not None and self.service.calls == [("hello", "account-9")]
