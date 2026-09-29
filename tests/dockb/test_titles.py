"""Tests for the path-segment safety rule shared by the API and the document store."""

from __future__ import annotations

import pytest

from dockb.titles import is_unsafe_segment, validate_segment


class TestIsUnsafeSegment:
    @pytest.mark.parametrize("value", ["", ".", "..", "a/b", "/", "a\\b", "\\", "../escape", "a/../../b"])
    def test_rejects_a_climbing_or_empty_value(self, value):
        assert is_unsafe_segment(value) is True

    @pytest.mark.parametrize("value", ["\x00", "\n", "\r", "\t", "a\x00b", "a\nb", "\x7f", "a\x1fb"])
    def test_rejects_control_characters(self, value):
        assert is_unsafe_segment(value) is True

    @pytest.mark.parametrize(
        "value",
        ["Faith", "Chapter 1", "...", "..a", "a..", ".hidden", "  ", "Act I", "emoji \U0001f600", "naïve"],
    )
    def test_accepts_an_ordinary_single_segment(self, value):
        assert is_unsafe_segment(value) is False


class TestValidateSegment:
    def test_raises_on_an_unsafe_value(self):
        with pytest.raises(ValueError, match="not a valid title"):
            validate_segment("../escape")

    def test_error_names_the_offending_value(self):
        with pytest.raises(ValueError, match="'a/b'"):
            validate_segment("a/b")

    def test_returns_nothing_for_a_safe_value(self):
        assert validate_segment("Faith") is None
