"""Backend proofreading: spelling, grammar and style checks over one paragraph.

LanguageTool is the checking engine. It runs as a local server (managed by
``language_tool_python``) and is reached only from here, so the editor never
sees the engine and the manuscript text never leaves the process. The service is
interactive-only: it reads a paragraph and answers diagnostics, and never writes
a file, the graph, or a snapshot.

Diagnostics carry paragraph-relative character offsets (``start``/``end``) plus
the rule, category, severity, message and replacements. The frontend maps those
offsets onto its own displayed sentence text, so the same answer decorates both
the WYSIWYG and the raw view.
"""

from __future__ import annotations

import logging
import os
import string
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, cast

from cachetools import TTLCache

logger = logging.getLogger(__name__)

DEFAULT_LANGUAGE = "en-US"

MAX_TEXT_CHARS = 20000

SUPPORTED_LANGUAGES: tuple[tuple[str, str], ...] = (
    ("en-US", "English (US)"),
    ("en-GB", "English (UK)"),
    ("en-AU", "English (AU)"),
    ("en-CA", "English (CA)"),
    ("de", "Deutsch"),
    ("fr", "Français"),
    ("es", "Español"),
    ("it", "Italiano"),
    ("pt", "Português"),
    ("nl", "Nederlands"),
    ("sv", "Svenska"),
    ("pl", "Polski"),
)

_ToolFactory = Callable[[str], Any]


class ProofreadingError(RuntimeError):
    """Base class for proofreading failures the route reports."""


class ProofreadingDisabledError(ProofreadingError):
    """Proofreading is turned off by configuration."""


class ProofreadingUnavailableError(ProofreadingError):
    """The checking engine could not be started or reached."""


class UnsupportedLanguageError(ProofreadingError):
    """The requested language is not in the supported set."""


class TextTooLongError(ProofreadingError):
    """The paragraph is longer than the service checks in one request."""


@dataclass(frozen=True)
class QuotePair:
    """A paired quote fix: what the flagged quote and its partner should become.

    The flagged (main) position is the diagnostic's own ``start``/``end``;
    ``replacement`` is its correct character. ``partner_start``/``partner_end``
    name the partner quote and ``partner_replacement`` its correct character.
    """

    replacement: str
    partner_start: int
    partner_end: int
    partner_replacement: str


@dataclass(frozen=True)
class Diagnostic:
    """One proofreading finding, anchored to paragraph-relative offsets."""

    rule_id: str
    category: str
    severity: str
    message: str
    start: int
    end: int
    replacements: tuple[str, ...] = ()
    pair: QuotePair | None = None
    in_focus: bool = False


@dataclass
class ProofreadingService:  # pylint: disable=too-few-public-methods
    """Checks one paragraph at a time with a lazily started LanguageTool engine."""

    enabled: bool = True
    default_language: str = DEFAULT_LANGUAGE
    tool_factory: _ToolFactory | None = None

    _tools: dict[str, Any] = field(default_factory=dict, init=False, repr=False)
    _cache: Any = field(default=None, init=False, repr=False)
    _lock: Any = field(default_factory=threading.Lock, init=False, repr=False)

    def __post_init__(self) -> None:
        if self.default_language not in {code for code, _label in SUPPORTED_LANGUAGES}:
            self.default_language = DEFAULT_LANGUAGE
        if self.tool_factory is None:
            self.tool_factory = _default_tool_factory
        self._cache = TTLCache(maxsize=256, ttl=300)

    def supported_languages(self) -> list[tuple[str, str]]:
        """The languages the editor may select, as ``(code, label)`` pairs."""
        return list(SUPPORTED_LANGUAGES)

    def check(  # pylint: disable=too-many-arguments,too-many-positional-arguments
        self,
        text: str,
        language: str | None = None,
        focus_start: int | None = None,
        focus_end: int | None = None,
        accepted_words: tuple[str, ...] = (),
    ) -> list[Diagnostic]:
        """Return the diagnostics for *text*, paragraph-relative and cached."""
        if not self.enabled:
            raise ProofreadingDisabledError("proofreading is disabled")
        language = self._resolve_language(language)
        if len(text) > MAX_TEXT_CHARS:
            raise TextTooLongError(
                f"text is {len(text)} characters; the limit is {MAX_TEXT_CHARS}",
            )
        accepted = tuple(
            sorted({word.strip().casefold() for word in accepted_words if word.strip()}),
        )
        key = (language, text, focus_start, focus_end, accepted)
        cached = cast("list[Diagnostic] | None", self._cache.get(key))
        if cached is not None:
            return cached
        tool = self._tool_for(language)
        try:
            with self._lock:
                matches = tool.check(text)
        except Exception as exc:  # pylint: disable=broad-except
            raise ProofreadingUnavailableError(str(exc)) from exc
        diagnostics = [
            diagnostic
            for match in matches
            if (
                diagnostic := _to_diagnostic(
                    match,
                    text,
                    focus_start,
                    focus_end,
                    accepted,
                )
            )
            is not None
        ]
        self._cache[key] = diagnostics
        return diagnostics

    def close(self) -> None:
        """Stop every engine this service started."""
        with self._lock:
            tools = list(self._tools.values())
            self._tools.clear()
        for tool in tools:
            try:
                tool.close()
            except Exception:  # pylint: disable=broad-except
                logger.warning("failed to stop a proofreading engine", exc_info=True)
        self._cache.clear()

    def _resolve_language(self, language: str | None) -> str:
        language = language or self.default_language
        if language not in {code for code, _label in SUPPORTED_LANGUAGES}:
            raise UnsupportedLanguageError(f"unsupported language: {language}")
        return language

    def _tool_for(self, language: str) -> Any:
        with self._lock:
            tool = self._tools.get(language)
            if tool is not None:
                return tool
            try:
                tool = self.tool_factory(language)  # type: ignore[misc]
            except Exception as exc:  # pylint: disable=broad-except
                raise ProofreadingUnavailableError(str(exc)) from exc
            self._tools[language] = tool
            return tool


def _default_tool_factory(language: str) -> Any:
    try:
        import language_tool_python  # pylint: disable=import-outside-toplevel
    except ImportError as exc:
        raise ProofreadingUnavailableError("language_tool_python is not installed") from exc
    url = os.environ.get("DOCKB_LANGUAGETOOL_URL", "").strip()
    if url:
        return language_tool_python.LanguageTool(language, remote_server=url)
    return language_tool_python.LanguageTool(language)


def _to_diagnostic(
    match: Any,
    text: str,
    focus_start: int | None,
    focus_end: int | None,
    accepted: tuple[str, ...],
) -> Diagnostic | None:
    offset = _as_int(getattr(match, "offset", 0))
    length = _as_int(getattr(match, "error_length", getattr(match, "length", 0)))
    if offset < 0 or offset >= len(text) or length <= 0:
        return None
    end = min(offset + length, len(text))
    if end <= offset:
        return None
    rule_id = str(getattr(match, "rule_id", "") or "")
    category = str(getattr(match, "category", "") or "")
    issue_type = str(getattr(match, "rule_issue_type", "") or "").strip().lower()
    if _is_spelling(rule_id, category, issue_type) and _word_at(text, offset, end) in accepted:
        return None
    replacements = tuple(str(replacement) for replacement in (getattr(match, "replacements", ()) or ()))
    message = str(getattr(match, "message", "") or "")
    in_focus = focus_start is not None and focus_end is not None and offset < focus_end and end > focus_start
    return Diagnostic(
        rule_id=rule_id,
        category=category,
        severity="info" if issue_type in _INFORMATIONAL_ISSUES else "warning",
        message=message,
        start=offset,
        end=end,
        replacements=replacements,
        pair=_find_quote_pair(text, offset, end, rule_id, message),
        in_focus=in_focus,
    )


_INFORMATIONAL_ISSUES = frozenset({"style", "uncategorized"})
_SPELLING_ISSUES = frozenset({"misspelling", "typographical"})
_SPELLING_CATEGORIES = frozenset({"TYPOS"})


def _is_spelling(rule_id: str, category: str, issue_type: str) -> bool:
    return issue_type in _SPELLING_ISSUES or category.upper() in _SPELLING_CATEGORIES or rule_id.startswith("MORFOLOGIK_RULE")


def _word_at(text: str, start: int, end: int) -> str:
    return text[start:end].strip(string.punctuation + string.whitespace).casefold()


def _as_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


_QUOTE_RULES = frozenset({"EN_QUOTES", "EN_UNPAIRED_BRACKETS", "UNPAIRED_BRACKETS"})
_QUOTE_CHARS = frozenset({'"', "'", "\u201c", "\u201d", "\u2018", "\u2019"})
_OPEN_DOUBLE = "\u201c"
_CLOSE_DOUBLE = "\u201d"
_OPEN_SINGLE = "\u2018"
_CLOSE_SINGLE = "\u2019"
_DOUBLE_QUOTES = frozenset({'"', _OPEN_DOUBLE, _CLOSE_DOUBLE})
_CLOSERS_DOUBLE = frozenset({'"', _CLOSE_DOUBLE})
_OPENERS_DOUBLE = frozenset({'"', _OPEN_DOUBLE})
_CLOSERS_SINGLE = frozenset({"'", _CLOSE_SINGLE})
_OPENERS_SINGLE = frozenset({"'", _OPEN_SINGLE})


def _find_quote_pair(text: str, offset: int, end: int, rule_id: str, message: str) -> QuotePair | None:
    """Return the pair fix for a flagged quote, or ``None`` when there is no partner.

    LanguageTool flags one quote at a time and never says where its partner is, so
    the partner is re-found by scanning the same paragraph for the nearest opposite
    quote of the same kind (double or single). The result is best-effort: apostrophes
    and nested quotes can occasionally mis-pair, which the caller accepts.
    """
    if rule_id not in _QUOTE_RULES or end - offset != 1:
        return None
    char = text[offset:end]
    if char not in _QUOTE_CHARS:
        return None
    double = char in _DOUBLE_QUOTES
    role = _quote_role(text, offset, message)
    partner = _next_closer(text, end, double) if role == "open" else _prev_opener(text, offset, double)
    if partner is None:
        return None
    opener = _OPEN_DOUBLE if double else _OPEN_SINGLE
    closer = _CLOSE_DOUBLE if double else _CLOSE_SINGLE
    return QuotePair(closer, partner, partner + 1, opener) if role == "close" else QuotePair(opener, partner, partner + 1, closer)


def _quote_role(text: str, index: int, message: str) -> str:
    """Whether the flagged quote opens or closes a pair.

    Curly quotes say it outright; a straight quote borrows the message's
    "opening"/"closing", and falls back to the next character (a word following a
    straight quote marks it as an opener).
    """
    char = text[index]
    if char in (_OPEN_DOUBLE, _OPEN_SINGLE):
        return "open"
    if char in (_CLOSE_DOUBLE, _CLOSE_SINGLE):
        return "close"
    lowered = message.lower()
    if "closing" in lowered:
        return "close"
    if "opening" in lowered:
        return "open"
    after = index + 1
    return "open" if after < len(text) and text[after].isalpha() else "close"


def _next_closer(text: str, start: int, double: bool) -> int | None:
    candidates = _CLOSERS_DOUBLE if double else _CLOSERS_SINGLE
    for index in range(start, len(text)):
        char = text[index]
        if char in candidates and (double or not _is_apostrophe(text, index)):
            return index
    return None


def _prev_opener(text: str, start: int, double: bool) -> int | None:
    candidates = _OPENERS_DOUBLE if double else _OPENERS_SINGLE
    for index in range(start - 1, -1, -1):
        char = text[index]
        if char in candidates and (double or not _is_apostrophe(text, index)):
            return index
    return None


def _is_apostrophe(text: str, index: int) -> bool:
    before = index - 1 >= 0 and text[index - 1].isalnum()
    after = index + 1 < len(text) and text[index + 1].isalnum()
    return before and after
