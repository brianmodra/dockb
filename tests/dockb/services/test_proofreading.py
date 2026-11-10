"""Tests for the LanguageTool-backed proofreading service."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field

import pytest

from dockb.services.proofreading import (
    DEFAULT_LANGUAGE,
    MAX_TEXT_CHARS,
    ProofreadingDisabledError,
    ProofreadingService,
    ProofreadingUnavailableError,
    TextTooLongError,
    UnsupportedLanguageError,
)


@dataclass
class _Match:
    rule_id: str = "MORFOLOGIK_RULE_EN_US"
    category: str = "TYPOS"
    rule_issue_type: str = "misspelling"
    message: str = "Possible spelling mistake"
    offset: int = 0
    error_length: int = 3
    replacements: list[str] = field(default_factory=lambda: ["the"])


class _FakeTool:  # pylint: disable=too-few-public-methods
    def __init__(self, matches: list[_Match], *, error: Exception | None = None) -> None:
        self.matches = matches
        self.error = error
        self.calls: list[str] = []
        self.closed = False

    def check(self, text: str) -> list[_Match]:
        self.calls.append(text)
        if self.error is not None:
            raise self.error
        return self.matches

    def close(self) -> None:
        self.closed = True


class _ToolFactory:  # pylint: disable=too-few-public-methods
    def __init__(self, tool: _FakeTool) -> None:
        self.tool = tool
        self.languages: list[str] = []

    def __call__(self, language: str) -> _FakeTool:
        self.languages.append(language)
        return self.tool


def _service(tool: _FakeTool, **kwargs: object) -> tuple[ProofreadingService, _ToolFactory]:
    factory = _ToolFactory(tool)
    service = ProofreadingService(tool_factory=factory, **kwargs)  # type: ignore[arg-type]
    return service, factory


class TestCheck:
    def test_normalizes_a_match_to_a_paragraph_relative_diagnostic(self) -> None:
        service, _ = _service(
            _FakeTool(
                [
                    _Match(
                        rule_id="MORFOLOGIK_RULE_EN_US",
                        category="TYPOS",
                        rule_issue_type="misspelling",
                        message="Possible spelling mistake",
                        offset=4,
                        error_length=3,
                        replacements=["the", "then"],
                    )
                ]
            )
        )

        [diagnostic] = service.check("the teh cat", "en-US")

        assert diagnostic.rule_id == "MORFOLOGIK_RULE_EN_US"
        assert diagnostic.category == "TYPOS"
        assert diagnostic.severity == "warning"
        assert diagnostic.message == "Possible spelling mistake"
        assert (diagnostic.start, diagnostic.end) == (4, 7)
        assert diagnostic.replacements == ("the", "then")

    def test_marks_diagnostics_overlapping_the_focused_sentence(self) -> None:
        service, _ = _service(
            _FakeTool([_Match(offset=0, error_length=3)]),
        )

        [inside] = service.check("teh cat. good dog.", "en-US", focus_start=0, focus_end=9)
        [outside] = service.check("teh cat. good dog.", "en-US", focus_start=9, focus_end=18)

        assert inside.in_focus is True
        assert outside.in_focus is False

    def test_accepted_words_suppress_their_spelling_diagnostic(self) -> None:
        service, _ = _service(
            _FakeTool([_Match(offset=0, error_length=7, replacements=["Karakas"])]),
        )

        assert service.check("Karakas", "en-US", accepted_words=("karakas",)) == []
        assert len(service.check("Karakas", "en-US", accepted_words=())) == 1

    def test_a_non_spelling_match_is_not_filtered_by_the_glossary(self) -> None:
        service, _ = _service(
            _FakeTool(
                [
                    _Match(
                        rule_id="EN_A_VS_AN",
                        category="GRAMMAR",
                        rule_issue_type="grammar",
                        message="Use 'an'",
                        offset=0,
                        error_length=1,
                    )
                ]
            )
        )

        assert len(service.check("a apple", "en-US", accepted_words=("a",))) == 1

    def test_style_findings_are_information(self) -> None:
        service, _ = _service(
            _FakeTool([_Match(rule_id="STYLE_RULE", category="STYLE", rule_issue_type="style")]),
        )

        [diagnostic] = service.check("text", "en-US")

        assert diagnostic.severity == "info"

    def test_reuses_the_answer_for_the_same_request(self) -> None:
        tool = _FakeTool([_Match()])
        service, factory = _service(tool)

        service.check("the teh cat", "en-US")
        service.check("the teh cat", "en-US")

        assert tool.calls == ["the teh cat"]
        assert factory.languages == ["en-US"]

    def test_the_default_language_is_used_when_none_is_named(self) -> None:
        service, factory = _service(_FakeTool([]), default_language="fr")

        service.check("bonjour", None)

        assert factory.languages == ["fr"]
        assert service.default_language == "fr"

    def test_an_unsupported_default_language_falls_back_to_english(self) -> None:
        service, factory = _service(_FakeTool([]), default_language="klingon")

        service.check("hello", None)

        assert service.default_language == DEFAULT_LANGUAGE
        assert factory.languages == [DEFAULT_LANGUAGE]

    def test_an_unsupported_language_is_rejected(self) -> None:
        service, _ = _service(_FakeTool([]))

        with pytest.raises(UnsupportedLanguageError):
            service.check("hello", "klingon")

    def test_oversized_text_is_rejected(self) -> None:
        service, _ = _service(_FakeTool([]))

        with pytest.raises(TextTooLongError):
            service.check("x" * (MAX_TEXT_CHARS + 1), "en-US")

    def test_disabled_service_refuses_to_check(self) -> None:
        service, factory = _service(_FakeTool([]), enabled=False)

        with pytest.raises(ProofreadingDisabledError):
            service.check("hello", "en-US")
        assert not factory.languages

    def test_an_engine_that_cannot_start_is_reported_as_unavailable(self) -> None:
        def factory(_language: str) -> _FakeTool:
            raise RuntimeError("no java")

        service = ProofreadingService(tool_factory=factory)

        with pytest.raises(ProofreadingUnavailableError):
            service.check("hello", "en-US")

    def test_an_engine_failure_is_reported_as_unavailable(self) -> None:
        service, _ = _service(_FakeTool([], error=RuntimeError("crashed")))

        with pytest.raises(ProofreadingUnavailableError):
            service.check("hello", "en-US")

    def test_an_engine_is_never_checked_concurrently(self) -> None:
        active = 0
        high_water = 0
        state_lock = threading.Lock()

        class _SlowTool:  # pylint: disable=too-few-public-methods
            def check(self, _text: str) -> list[_Match]:
                nonlocal active, high_water
                with state_lock:
                    active += 1
                    high_water = max(high_water, active)
                time.sleep(0.05)
                with state_lock:
                    active -= 1
                return []

            def close(self) -> None:
                pass

        tool = _SlowTool()
        service = ProofreadingService(tool_factory=lambda _language: tool)

        threads = [threading.Thread(target=service.check, args=(text, "en-US")) for text in ("one", "two")]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        assert high_water == 1

    def test_close_stops_every_started_engine(self) -> None:
        tool = _FakeTool([])
        service, _ = _service(tool)
        service.check("one", "en-US")

        service.close()

        assert tool.closed is True

    def test_supported_languages_include_the_default(self) -> None:
        service, _ = _service(_FakeTool([]))

        codes = [code for code, _label in service.supported_languages()]

        assert DEFAULT_LANGUAGE in codes
