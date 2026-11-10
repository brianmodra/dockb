"""Tests for POST /api/check."""

from __future__ import annotations

from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from dockb.controllers.auth import get_current_user, get_owner
from dockb.controllers.glossary import set_glossary_service
from dockb.controllers.proofreading import check, set_proofreading_service
from dockb.exceptions import DocumentNotFoundError
from dockb.services.proofreading import (
    Diagnostic,
    ProofreadingDisabledError,
    ProofreadingService,
    ProofreadingUnavailableError,
    TextTooLongError,
    UnsupportedLanguageError,
)


def _make_app() -> FastAPI:
    app = FastAPI()
    app.dependency_overrides[get_owner] = lambda: "account-0"
    app.dependency_overrides[get_current_user] = lambda: "abby"
    app.add_api_route("/api/check", check, methods=["POST"])
    return app


class _StubService:  # pylint: disable=too-few-public-methods
    default_language = "en-US"

    def __init__(self, diagnostics: list[Diagnostic] | None = None, error: Exception | None = None) -> None:
        self.diagnostics = diagnostics or []
        self.error = error
        self.calls: list[tuple[object, ...]] = []

    def check(
        self,
        text: str,
        language: str | None = None,
        focus_start: int | None = None,
        focus_end: int | None = None,
        accepted_words: tuple[str, ...] = (),
    ) -> list[Diagnostic]:
        self.calls.append((text, language, focus_start, focus_end, accepted_words))
        if self.error is not None:
            raise self.error
        return self.diagnostics


class _StubGlossary:  # pylint: disable=too-few-public-methods
    def __init__(self, words: tuple[str, ...] = (), error: Exception | None = None) -> None:
        self.words = words
        self.error = error
        self.calls: list[tuple[str | None, str, str]] = []

    def effective_words(self, document_id: str | None, *, owner: str, username: str) -> tuple[str, ...]:
        self.calls.append((document_id, owner, username))
        if self.error is not None:
            raise self.error
        return self.words


class TestCheckRoute:
    def setup_method(self) -> None:
        self.client = TestClient(_make_app())

    def teardown_method(self) -> None:
        set_proofreading_service(None)
        set_glossary_service(None)
        self.client.app.dependency_overrides.pop(get_owner, None)
        self.client.app.dependency_overrides.pop(get_current_user, None)

    def _wire(self, service: _StubService) -> None:
        set_proofreading_service(service)

    def test_returns_the_normalized_diagnostics(self) -> None:
        self._wire(
            _StubService(
                [
                    Diagnostic(
                        rule_id="MORFOLOGIK_RULE_EN_US",
                        category="TYPOS",
                        severity="warning",
                        message="Possible spelling mistake",
                        start=4,
                        end=7,
                        replacements=("the",),
                        in_focus=True,
                    )
                ]
            )
        )

        resp = self.client.post("/api/check", json={"text": "the teh cat", "language": "en-US"})

        assert resp.status_code == 200
        assert resp.json() == {
            "language": "en-US",
            "diagnostics": [
                {
                    "rule_id": "MORFOLOGIK_RULE_EN_US",
                    "category": "TYPOS",
                    "severity": "warning",
                    "message": "Possible spelling mistake",
                    "start": 4,
                    "end": 7,
                    "replacements": ["the"],
                    "in_focus": True,
                }
            ],
        }

    def test_without_a_service_answers_503(self) -> None:
        resp = self.client.post("/api/check", json={"text": "hello"})
        assert resp.status_code == 503

    def test_a_disabled_service_answers_503(self) -> None:
        self._wire(_StubService(error=ProofreadingDisabledError("off")))
        resp = self.client.post("/api/check", json={"text": "hello"})
        assert resp.status_code == 503

    def test_an_unavailable_engine_answers_503(self) -> None:
        self._wire(_StubService(error=ProofreadingUnavailableError("no java")))
        resp = self.client.post("/api/check", json={"text": "hello"})
        assert resp.status_code == 503

    def test_an_unsupported_language_answers_422(self) -> None:
        self._wire(_StubService(error=UnsupportedLanguageError("klingon")))
        resp = self.client.post("/api/check", json={"text": "hello", "language": "klingon"})
        assert resp.status_code == 422

    def test_oversized_text_answers_422(self) -> None:
        self._wire(_StubService(error=TextTooLongError("too long")))
        resp = self.client.post("/api/check", json={"text": "hello"})
        assert resp.status_code == 422

    def test_an_empty_paragraph_is_rejected(self) -> None:
        self._wire(_StubService())
        resp = self.client.post("/api/check", json={"text": ""})
        assert resp.status_code == 422

    def test_the_focus_is_forwarded(self) -> None:
        service = _StubService()
        self._wire(service)
        resp = self.client.post(
            "/api/check",
            json={
                "text": "the teh cat",
                "language": "en-GB",
                "document_id": "d1",
                "paragraph_id": "p1",
                "focus": {"start": 4, "end": 7},
            },
        )
        assert resp.status_code == 200
        assert service.calls == [("the teh cat", "en-GB", 4, 7, ())]

    def test_the_default_language_names_the_response_when_none_is_sent(self) -> None:
        self._wire(_StubService())
        resp = self.client.post("/api/check", json={"text": "hello"})
        assert resp.status_code == 200
        assert resp.json()["language"] == "en-US"

    def test_the_documents_effective_glossary_is_forwarded_to_the_checker(self) -> None:
        service = _StubService()
        glossary = _StubGlossary(words=("Karakas",))
        self._wire(service)
        set_glossary_service(glossary)

        resp = self.client.post("/api/check", json={"text": "Karakas", "document_id": "doc-1"})

        assert resp.status_code == 200
        assert glossary.calls == [("doc-1", "account-0", "abby")]
        assert service.calls == [("Karakas", None, None, None, ("Karakas",))]

    def test_an_accepted_character_name_suppresses_its_spelling_diagnostic(self) -> None:
        class _SpellingTool:  # pylint: disable=too-few-public-methods
            def check(self, _text: str) -> list[SimpleNamespace]:
                return [
                    SimpleNamespace(
                        rule_id="MORFOLOGIK_RULE_EN_US",
                        category="TYPOS",
                        rule_issue_type="misspelling",
                        message="Possible spelling mistake",
                        offset=0,
                        error_length=7,
                        replacements=["Karakas"],
                    )
                ]

            def close(self) -> None:
                pass

        set_proofreading_service(ProofreadingService(tool_factory=lambda _language: _SpellingTool()))
        set_glossary_service(_StubGlossary(words=("Karakas",)))

        resp = self.client.post("/api/check", json={"text": "Karakas", "document_id": "doc-1"})

        assert resp.status_code == 200
        assert resp.json()["diagnostics"] == []

    def test_an_absent_document_answers_404(self) -> None:
        self._wire(_StubService())
        set_glossary_service(_StubGlossary(error=DocumentNotFoundError("doc-1")))

        resp = self.client.post("/api/check", json={"text": "hello", "document_id": "doc-1"})

        assert resp.status_code == 404
