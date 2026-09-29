"""Tests for path-segment safety on document and chapter attrs."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from dockb.controllers.schemas.documents import DocumentAttrs
from dockb.controllers.schemas.nodes import ChapterAttrs

UNSAFE = ["a/b", "../escape", "..", ".", "a\\b", "back\\slash", "nul\x00", "newline\n", "del\x7f"]


class TestDocumentAttrsTitle:
    @pytest.mark.parametrize("title", UNSAFE)
    def test_rejects_an_unsafe_title(self, title):
        with pytest.raises(ValidationError):
            DocumentAttrs(title=title, author="Wes Almond")

    @pytest.mark.parametrize("title", ["", "   "])
    def test_still_rejects_a_blank_title(self, title):
        with pytest.raises(ValidationError):
            DocumentAttrs(title=title, author="Wes Almond")

    @pytest.mark.parametrize("title", ["Faith", "...", "Linchpin", "Book 1: The Beginning"])
    def test_accepts_an_ordinary_title(self, title):
        assert DocumentAttrs(title=title, author="Wes Almond").title == title

    def test_error_message_names_the_title(self):
        with pytest.raises(ValidationError, match="a/b"):
            DocumentAttrs(title="a/b", author="Wes Almond")


class TestChapterAttrsTitle:
    @pytest.mark.parametrize("title", UNSAFE)
    def test_rejects_an_unsafe_title(self, title):
        with pytest.raises(ValidationError):
            ChapterAttrs(title=title)

    @pytest.mark.parametrize("title", ["", "   "])
    def test_still_rejects_a_blank_title(self, title):
        with pytest.raises(ValidationError):
            ChapterAttrs(title=title)

    def test_error_message_names_the_title(self):
        with pytest.raises(ValidationError, match="a/b"):
            ChapterAttrs(title="a/b")


@pytest.mark.parametrize("title", ["Faith", "Opening 1", "...", ".hidden", "naïve", "emoji \U0001f600", "Act I", "a..", "..a"])
def test_a_storable_title_reaches_the_api(title):
    """A title the store can place on disk must be accepted by the API.

    The store's rule is filesystem safety and the schema's is that plus "not
    blank". A title the store happily turns into a path but the API refuses
    would be a contract the editor cannot satisfy. Blank titles are the one
    intended exception: a whitespace-only name is a legal directory but a
    meaningless title.
    """
    assert ChapterAttrs(title=title).title == title
    assert DocumentAttrs(title=title, author="Author").title == title


class TestChapterAttrsAct:
    @pytest.mark.parametrize("act", ["../../x", "Act ../../x", "a/b", "..", "nul\x00"])
    def test_rejects_an_unsafe_act(self, act):
        with pytest.raises(ValidationError):
            ChapterAttrs(title="Faith", act=act)

    @pytest.mark.parametrize("act", ["", "I", "Act I", "Book Two", "..."])
    def test_accepts_an_ordinary_act_including_the_empty_one(self, act):
        assert ChapterAttrs(title="Faith", act=act).act == act
