"""Tests for shared front-matter parsing, rendering, and merging."""

from __future__ import annotations

import pytest

from dockb.exceptions import ChapterMismatchError
from dockb.infrastructure.markdown import front_matter


class TestParse:
    def test_returns_attrs_and_body(self):
        attrs, body = front_matter.parse('---\nid: c1\ntitle: "Chapter 1"\n---\n\nBody here.\n')
        assert attrs == {"id": "c1", "title": "Chapter 1"}
        assert body == "\nBody here.\n"

    def test_absent_front_matter_returns_empty_attrs_and_whole_content(self):
        attrs, body = front_matter.parse("Just body text.\n\nSecond paragraph.")
        assert not attrs
        assert body == "Just body text.\n\nSecond paragraph."

    def test_unclosed_front_matter_raises(self):
        with pytest.raises(ChapterMismatchError, match="closing"):
            front_matter.parse("---\nid: c1\n\nBody.")

    def test_non_mapping_front_matter_raises(self):
        with pytest.raises(ChapterMismatchError, match="mapping"):
            front_matter.parse("---\n- a\n- b\n---\n\nBody.")

    def test_id_inside_body_is_not_front_matter(self):
        attrs, body = front_matter.parse("Body with --- dashes --- inside.")
        assert not attrs
        assert body == "Body with --- dashes --- inside."


class TestRender:
    def test_renders_delimited_yaml_block(self):
        assert front_matter.render({"id": "c1", "title": "Chapter 1"}) == "---\nid: c1\ntitle: Chapter 1\n---\n"

    def test_preserves_given_key_order(self):
        assert front_matter.render({"title": "T", "id": "c1"}) == "---\ntitle: T\nid: c1\n---\n"


class TestMerge:
    def test_prepends_block_when_absent(self):
        merged = front_matter.merge("Body.", {"id": "c1", "title": "T"})
        assert merged == "---\nid: c1\ntitle: T\n---\nBody."

    def test_overwrites_known_keys_and_keeps_others(self):
        content = "---\nauthor: Brian\ntitle: Old\n---\n\nBody.\n"
        merged = front_matter.merge(content, {"id": "c1", "title": "New"})
        assert merged == "---\nauthor: Brian\ntitle: New\nid: c1\n---\n\nBody.\n"

    def test_adds_new_keys_after_existing_ones(self):
        content = "---\nauthor: Brian\n---\n\nBody.\n"
        merged = front_matter.merge(content, {"id": "c1", "title": "T"})
        assert merged == "---\nauthor: Brian\nid: c1\ntitle: T\n---\n\nBody.\n"
