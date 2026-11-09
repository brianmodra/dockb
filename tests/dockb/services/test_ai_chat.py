"""Tests for the AI chat service and its MCP hand-off (README_mcp_auth.md §2)."""

from __future__ import annotations

import uuid
from typing import Any

import pytest

from dockb.services.ai_chat import (
    _DEFAULT_MODEL,
    _MODEL_ENV_VAR,
    AiChatService,
    MissingApiKeyError,
)

_PUBLIC_URL_ENV_VAR = "DOCKB_MCP_PUBLIC_URL"


class _StubIssuer:  # pylint: disable=too-few-public-methods
    def __init__(self) -> None:
        self.mints: list[tuple[str, str]] = []

    def mint(self, prompt_id: str, account_id: str) -> str:
        self.mints.append((prompt_id, account_id))
        return f"token-for-{prompt_id}"


class TestCompleteSignature:
    """complete() sends the prompt and returns the model's reply."""

    def test_prompt_passes_to_the_model_and_reply_comes_back(self) -> None:
        seen: list[tuple[str, str | None, str | None, str | None]] = []

        def complete(prompt: str, token: str | None, server_url: str | None, document_id: str | None = None) -> str:
            seen.append((prompt, token, server_url, document_id))
            return "the reply"

        service = AiChatService(complete=complete)
        assert service.complete("what about chapter 2?", "account-1") == "the reply"
        assert seen == [("what about chapter 2?", None, None, None)]

    def test_the_open_document_is_forwarded_to_the_call(self) -> None:
        seen: list[tuple[str, str | None, str | None, str | None]] = []

        def complete(prompt: str, token: str | None, server_url: str | None, document_id: str | None = None) -> str:
            seen.append((prompt, token, server_url, document_id))
            return "the reply"

        service = AiChatService(complete=complete)
        assert service.complete("what about chapter 2?", "account-1", document_id="d1") == "the reply"
        assert seen == [("what about chapter 2?", None, None, "d1")]

    def test_a_live_issuer_mints_a_token_bound_to_the_account(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv(_PUBLIC_URL_ENV_VAR, "https://mcp.example.com")
        issuer = _StubIssuer()
        seen: list[tuple[str, str | None, str | None, str | None]] = []

        def complete(prompt: str, token: str | None, server_url: str | None, document_id: str | None = None) -> str:
            seen.append((prompt, token, server_url, document_id))
            return "the reply"

        service = AiChatService(complete=complete, token_issuer=lambda: issuer)
        service.complete("hello", "account-9")
        assert len(issuer.mints) == 1
        prompt_id, account = issuer.mints[0]
        assert account == "account-9"
        assert server_url_seen(seen) == "https://mcp.example.com/mcp"
        assert token_seen(seen) == f"token-for-{prompt_id}"

    def test_each_prompt_gets_its_own_prompt_id(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv(_PUBLIC_URL_ENV_VAR, "https://mcp.example.com")
        issuer = _StubIssuer()
        service = AiChatService(token_issuer=lambda: issuer, complete=lambda *_: "ok")
        service.complete("one", "account-1")
        service.complete("two", "account-1")
        assert len(issuer.mints) == 2
        assert issuer.mints[0][0] != issuer.mints[1][0]

    def test_minted_prompt_ids_are_unmistakable_handles(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv(_PUBLIC_URL_ENV_VAR, "https://mcp.example.com")
        issuer = _StubIssuer()
        service = AiChatService(token_issuer=lambda: issuer, complete=lambda *_: "ok")
        service.complete("one", "account-1")
        assert uuid.UUID(issuer.mints[0][0])

    def test_without_a_public_url_the_prompt_sends_without_mcp(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv(_PUBLIC_URL_ENV_VAR, raising=False)
        issuer = _StubIssuer()
        seen: list[tuple[str, str | None, str | None, str | None]] = []

        def complete(prompt: str, token: str | None, server_url: str | None, document_id: str | None = None) -> str:
            seen.append((prompt, token, server_url, document_id))
            return "the reply"

        service = AiChatService(complete=complete, token_issuer=lambda: issuer)
        service.complete("hello", "account-1")
        assert seen == [("hello", None, None, None)]
        assert not issued_mints(issuer)

    def test_without_an_issuer_the_prompt_sends_without_mcp(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv(_PUBLIC_URL_ENV_VAR, "https://mcp.example.com")
        seen: list[tuple[str, str | None, str | None, str | None]] = []

        def complete(prompt: str, token: str | None, server_url: str | None, document_id: str | None = None) -> str:
            seen.append((prompt, token, server_url, document_id))
            return "the reply"

        service = AiChatService(complete=complete, token_issuer=lambda: None)
        service.complete("hello", "account-1")
        assert seen == [("hello", None, None, None)]


def issued_mints(issuer: _StubIssuer) -> list[tuple[str, str]]:
    return list(issuer.mints)


def server_url_seen(seen: list[tuple[str, str | None, str | None, str | None]]) -> str | None:
    return seen[0][2]


def token_seen(seen: list[tuple[str, str | None, str | None, str | None]]) -> str | None:
    return seen[0][1]


class TestResponsesCall:
    """_openai_complete builds the Responses-API request."""

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
        AiChatService()._default_complete("hi", None, None)
        assert calls[0]["json"]["model"] == _DEFAULT_MODEL

    def test_model_comes_from_the_environment(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv(_MODEL_ENV_VAR, "gpt-4.1-mini")
        monkeypatch.setenv("OPENAI_API_KEY", "test-key")
        calls = self._post_capture(monkeypatch)
        AiChatService()._default_complete("hi", None, None)
        assert calls[0]["json"]["model"] == "gpt-4.1-mini"

    def test_the_call_is_one_user_message_with_the_raw_prompt(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("OPENAI_API_KEY", "test-key")
        monkeypatch.delenv(_PUBLIC_URL_ENV_VAR, raising=False)
        calls = self._post_capture(monkeypatch)
        AiChatService()._default_complete("  the prompt  ", None, None)
        assert calls[0]["url"] == "https://api.openai.com/v1/responses"
        assert calls[0]["json"]["input"] == [{"role": "user", "content": [{"type": "input_text", "text": "  the prompt  "}]}]
        assert "tools" not in calls[0]["json"]
        assert "instructions" not in calls[0]["json"]

    def test_the_reply_comes_from_the_output_message_items(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("OPENAI_API_KEY", "test-key")
        self._post_capture(monkeypatch)
        reply = AiChatService()._default_complete("hi", None, None)
        assert reply == "reply text"

    def test_the_reply_is_logged_to_the_backend_console(self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
        monkeypatch.setenv("OPENAI_API_KEY", "test-key")
        self._post_capture(monkeypatch)
        with caplog.at_level("INFO", logger="dockb.services.ai_chat"):
            AiChatService()._default_complete("hi", None, None)
        assert "reply text" in caplog.text

    def test_the_mcp_server_is_attached_with_the_token_in_authorization(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("OPENAI_API_KEY", "test-key")
        monkeypatch.setenv(_PUBLIC_URL_ENV_VAR, "https://mcp.example.com")
        calls = self._post_capture(monkeypatch)
        AiChatService()._default_complete("hi", "the-per-prompt-token", "https://mcp.example.com/mcp")
        tool = calls[0]["json"]["tools"][0]
        assert tool["type"] == "mcp"
        assert tool["server_label"] == "dockb"
        assert tool["server_url"] == "https://mcp.example.com/mcp"
        assert tool["authorization"] == "the-per-prompt-token"
        assert tool["require_approval"] == "never"
        assert tool["allowed_tools"] == ["find_paragraphs", "get_character_name"]

    def test_the_instructions_describe_the_mcp_server_but_never_hold_the_token(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("OPENAI_API_KEY", "test-key")
        monkeypatch.setenv(_PUBLIC_URL_ENV_VAR, "https://mcp.example.com")
        calls = self._post_capture(monkeypatch)
        AiChatService()._default_complete("hi", "the-per-prompt-token", "https://mcp.example.com/mcp")
        instructions = str(calls[0]["json"]["instructions"])
        assert "mcp.example.com/mcp" in instructions
        assert "dockb" in instructions.lower()
        assert "the-per-prompt-token" not in instructions
        assert "document" not in instructions.lower()
        assert calls[0]["json"]["input"][0]["content"][0]["text"] == "hi"

    def test_the_instructions_name_the_document_the_user_is_viewing(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("OPENAI_API_KEY", "test-key")
        monkeypatch.setenv(_PUBLIC_URL_ENV_VAR, "https://mcp.example.com")
        calls = self._post_capture(monkeypatch)
        AiChatService()._default_complete("hi", "the-per-prompt-token", "https://mcp.example.com/mcp", "d1")
        instructions = str(calls[0]["json"]["instructions"])
        assert "d1" in instructions
        assert "document_id" in instructions
        assert "the-per-prompt-token" not in instructions
        # the context rides in the instructions, never inside the user's text
        assert calls[0]["json"]["input"][0]["content"][0]["text"] == "hi"

    def test_the_instructions_teach_the_response_syntax_for_find_paragraphs(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("OPENAI_API_KEY", "test-key")
        monkeypatch.setenv(_PUBLIC_URL_ENV_VAR, "https://mcp.example.com")
        calls = self._post_capture(monkeypatch)
        AiChatService()._default_complete("hi", "the-per-prompt-token", "https://mcp.example.com/mcp")
        instructions = str(calls[0]["json"]["instructions"])
        assert '"response"' in instructions
        assert '"button"' in instructions
        assert '"highlight"' in instructions
        assert "chapter_id" in instructions
        assert "paragraph_id" in instructions
        # the button carries the sentences' positions, not their ids
        assert "sentence_indices" in instructions
        assert "sentence_ids" not in instructions
        # the tool marks the sentences it found; the button passes those positions on
        assert "matched_sentence_indexes" in instructions

    def test_the_instructions_treat_a_found_paragraph_as_a_candidate_to_verify(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """A word/name match is not an answer: the model must read the paragraph and judge it."""
        monkeypatch.setenv("OPENAI_API_KEY", "test-key")
        monkeypatch.setenv(_PUBLIC_URL_ENV_VAR, "https://mcp.example.com")
        calls = self._post_capture(monkeypatch)
        AiChatService()._default_complete("hi", "the-per-prompt-token", "https://mcp.example.com/mcp")
        instructions = str(calls[0]["json"]["instructions"]).lower()
        assert "candidate list, not an answer" in instructions
        assert "read each returned paragraph's sentences" in instructions
        assert "decide whether it answers" in instructions
        assert "related but does not answer" in instructions

    def test_the_instructions_pick_the_earliest_answering_paragraph(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """A first/earliest question takes the lowest chapter_index, then the lowest index."""
        monkeypatch.setenv("OPENAI_API_KEY", "test-key")
        monkeypatch.setenv(_PUBLIC_URL_ENV_VAR, "https://mcp.example.com")
        calls = self._post_capture(monkeypatch)
        AiChatService()._default_complete("hi", "the-per-prompt-token", "https://mcp.example.com/mcp")
        instructions = str(calls[0]["json"]["instructions"]).lower()
        assert "first or earliest occurrence" in instructions
        assert "reading order" in instructions
        assert "lower chapter_index" in instructions
        assert "lower index" in instructions
        assert "the paragraph's position" in instructions
        assert "skip any that do not actually answer" in instructions
        assert "earliest paragraph that does" in instructions
        assert "leave include_characters false" in instructions

    def test_the_instructions_describe_related_paragraphs_without_claiming_an_answer(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """A related paragraph is reported as related, and a summary stays question-independent."""
        monkeypatch.setenv("OPENAI_API_KEY", "test-key")
        monkeypatch.setenv(_PUBLIC_URL_ENV_VAR, "https://mcp.example.com")
        calls = self._post_capture(monkeypatch)
        AiChatService()._default_complete("hi", "the-per-prompt-token", "https://mcp.example.com/mcp")
        instructions = str(calls[0]["json"]["instructions"]).lower()
        assert "related but does not answer" in instructions
        assert "do not phrase it as an answer to the question" in instructions
        assert "assume the question's premise" in instructions
        assert "independent of the question" in instructions

    def test_the_response_syntax_is_taught_even_without_an_open_document(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("OPENAI_API_KEY", "test-key")
        monkeypatch.setenv(_PUBLIC_URL_ENV_VAR, "https://mcp.example.com")
        calls = self._post_capture(monkeypatch)
        AiChatService()._default_complete("hi", "the-per-prompt-token", "https://mcp.example.com/mcp")
        instructions = str(calls[0]["json"]["instructions"])
        assert '"highlight"' in instructions
        assert "document" not in instructions.lower()

    def test_the_mcp_call_forces_response_syntax_as_structured_output(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("OPENAI_API_KEY", "test-key")
        monkeypatch.setenv(_PUBLIC_URL_ENV_VAR, "https://mcp.example.com")
        calls = self._post_capture(monkeypatch)
        AiChatService()._default_complete("hi", "the-per-prompt-token", "https://mcp.example.com/mcp")
        text_format = calls[0]["json"]["text"]["format"]
        assert text_format["type"] == "json_schema"
        assert text_format["name"] == "response_syntax"
        assert text_format["strict"] is True
        schema = text_format["schema"]
        assert schema["type"] == "object"
        assert schema["required"] == ["response"]
        assert schema["additionalProperties"] is False
        response = schema["properties"]["response"]
        assert response["type"] == "array"
        items = response["items"]
        assert len(items["anyOf"]) == 2
        branches = {tuple(branch["required"]): branch for branch in items["anyOf"]}
        assert set(branches) == {("text",), ("button",)}
        assert branches[("text",)]["properties"]["text"] == {"type": "string"}
        assert branches[("text",)]["additionalProperties"] is False
        assert branches[("button",)]["additionalProperties"] is False
        button = branches[("button",)]["properties"]["button"]
        assert button["properties"]["function"] == {"type": "string", "enum": ["highlight"]}
        assert button["required"] == ["label", "function", "args"]
        assert button["additionalProperties"] is False
        args = button["properties"]["args"]
        assert args["required"] == ["chapter_id", "paragraph_id", "sentence_indices"]
        assert args["additionalProperties"] is False
        assert args["properties"]["sentence_indices"] == {"type": "array", "items": {"type": "integer"}}

    def test_structured_output_needs_both_the_url_and_a_token(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("OPENAI_API_KEY", "test-key")
        monkeypatch.setenv(_PUBLIC_URL_ENV_VAR, "https://mcp.example.com")
        calls = self._post_capture(monkeypatch)
        AiChatService()._default_complete("hi", None, "https://mcp.example.com/mcp")
        assert "text" not in calls[0]["json"]
        assert "instructions" not in calls[0]["json"]

    def test_without_mcp_the_call_does_not_force_structured_output(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("OPENAI_API_KEY", "test-key")
        monkeypatch.delenv(_PUBLIC_URL_ENV_VAR, raising=False)
        calls = self._post_capture(monkeypatch)
        AiChatService()._default_complete("hi", None, None)
        assert "text" not in calls[0]["json"]

    def test_the_response_syntax_instructions_demand_only_json(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("OPENAI_API_KEY", "test-key")
        monkeypatch.setenv(_PUBLIC_URL_ENV_VAR, "https://mcp.example.com")
        calls = self._post_capture(monkeypatch)
        AiChatService()._default_complete("hi", "the-per-prompt-token", "https://mcp.example.com/mcp")
        instructions = str(calls[0]["json"]["instructions"]).lower()
        assert "reply with only" in instructions
        assert "no prose" in instructions
        assert "code fences" in instructions
        assert '{"response": [{"text"' in instructions
        assert "never be empty" in instructions
        assert "a reply without json shows the reader plain text" not in instructions

    def test_the_instructions_ask_for_each_characters_names_before_searching(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """A character criterion needs the name forms, so the model calls get_character_name first."""
        monkeypatch.setenv("OPENAI_API_KEY", "test-key")
        monkeypatch.setenv(_PUBLIC_URL_ENV_VAR, "https://mcp.example.com")
        calls = self._post_capture(monkeypatch)
        AiChatService()._default_complete("hi", "the-per-prompt-token", "https://mcp.example.com/mcp")
        instructions = str(calls[0]["json"]["instructions"]).lower()
        assert "get_character_name" in instructions
        assert "character criteria" in instructions
        assert "first name" in instructions
        assert "middle names" in instructions
        assert "surname" in instructions
        assert "nicknames" in instructions

    def test_the_instructions_restrict_search_to_find_paragraphs_sentences(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Candidates are judged solely from find_paragraphs' sentences, without repeating the search."""
        monkeypatch.setenv("OPENAI_API_KEY", "test-key")
        monkeypatch.setenv(_PUBLIC_URL_ENV_VAR, "https://mcp.example.com")
        calls = self._post_capture(monkeypatch)
        AiChatService()._default_complete("hi", "the-per-prompt-token", "https://mcp.example.com/mcp")
        instructions = str(calls[0]["json"]["instructions"]).lower()
        assert "call find_paragraphs once" in instructions
        assert "solely from the sentences" in instructions
        assert "get_chapter" not in instructions


class TestResponsesErrorHandling:
    """Failed Responses-API calls log and surface the provider's error detail."""

    def test_an_incomplete_or_empty_model_reply_logs_and_raises(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        monkeypatch.setenv("OPENAI_API_KEY", "test-key")

        class IncompleteResponse:
            def raise_for_status(self) -> None:
                return None

            def json(self) -> dict[str, Any]:
                return {
                    "status": "incomplete",
                    "incomplete_details": {"reason": "max_output_tokens"},
                    "output": [{"type": "mcp_call"}],
                }

        monkeypatch.setattr("dockb.services.ai_chat.httpx2.post", lambda *_, **__: IncompleteResponse())
        with caplog.at_level("WARNING", logger="dockb.services.ai_chat"):
            with pytest.raises(RuntimeError, match=r"incomplete \(max_output_tokens\)"):
                AiChatService()._default_complete("hi", None, None)
        assert "incomplete (max_output_tokens)" in caplog.text

        class EmptyResponse:
            def raise_for_status(self) -> None:
                return None

            def json(self) -> dict[str, Any]:
                return {"status": "completed", "output": []}

        monkeypatch.setattr("dockb.services.ai_chat.httpx2.post", lambda *_, **__: EmptyResponse())
        with caplog.at_level("WARNING", logger="dockb.services.ai_chat"):
            with pytest.raises(RuntimeError, match="empty model reply"):
                AiChatService()._default_complete("hi", None, None)
        assert "empty model reply" in caplog.text

    def test_an_openai_error_logs_and_raises_the_response_error_message(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        monkeypatch.setenv("OPENAI_API_KEY", "test-key")

        class ErrorResponse:
            text = '{"error":{"message":"Context length exceeded","code":"context_length_exceeded"}}'

            def raise_for_status(self) -> None:
                raise RuntimeError("400 Bad Request")

            def json(self) -> dict[str, Any]:
                return {
                    "error": {
                        "message": "Context length exceeded",
                        "code": "context_length_exceeded",
                    }
                }

        monkeypatch.setattr("dockb.services.ai_chat.httpx2.post", lambda *_, **__: ErrorResponse())
        with caplog.at_level("WARNING", logger="dockb.services.ai_chat"):
            with pytest.raises(RuntimeError, match="context_length_exceeded: Context length exceeded"):
                AiChatService()._default_complete("hi", None, None)
        assert "context_length_exceeded: Context length exceeded" in caplog.text

    def test_a_non_json_error_body_falls_back_to_the_response_text(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        monkeypatch.setenv("OPENAI_API_KEY", "test-key")

        class PlainErrorResponse:
            text = "  upstream gateway timeout  "

            def raise_for_status(self) -> None:
                raise RuntimeError("502 Bad Gateway")

            def json(self) -> dict[str, Any]:
                raise ValueError("not json")

        monkeypatch.setattr("dockb.services.ai_chat.httpx2.post", lambda *_, **__: PlainErrorResponse())
        with caplog.at_level("WARNING", logger="dockb.services.ai_chat"):
            with pytest.raises(RuntimeError, match="upstream gateway timeout"):
                AiChatService()._default_complete("hi", None, None)
        assert "upstream gateway timeout" in caplog.text

    def test_a_whitespace_key_refuses_the_call(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("OPENAI_API_KEY", "   ")
        with pytest.raises(MissingApiKeyError):
            AiChatService()._default_complete("hi", None, None)


def _fake_response() -> Any:
    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, Any]:
            return {
                "output": [
                    {
                        "type": "message",
                        "content": [{"type": "output_text", "text": "reply text"}],
                    }
                ]
            }

    return FakeResponse()
