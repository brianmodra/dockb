"""Tests for POST /api/ai/chat."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from dockb.controllers.ai import chat, set_ai_service
from dockb.services.ai_chat import MissingApiKeyError


def _make_app() -> FastAPI:
    app = FastAPI()
    app.add_api_route("/api/ai/chat", chat, methods=["POST"])
    return app


class _StubService:  # pylint: disable=too-few-public-methods
    def __init__(self, reply: str = "the reply", error: Exception | None = None) -> None:
        self.reply = reply
        self.error = error
        self.prompts: list[str] = []

    def complete(self, prompt: str) -> str:
        self.prompts.append(prompt)
        if self.error is not None:
            raise self.error
        return self.reply


class TestChatRoute:
    """POST /api/ai/chat sends the prompt and returns the reply."""

    def setup_method(self) -> None:
        self.service: _StubService | None = None
        self.client = TestClient(_make_app())

    def teardown_method(self) -> None:
        set_ai_service(None)

    def _wire(self, service: _StubService) -> None:
        self.service = service
        set_ai_service(service)

    def test_returns_the_model_reply(self) -> None:
        self._wire(_StubService("answer"))
        resp = self.client.post("/api/ai/chat", json={"prompt": "hello"})
        assert resp.status_code == 200
        assert resp.json() == {"reply": "answer"}
        assert self.service is not None and self.service.prompts == ["hello"]

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
