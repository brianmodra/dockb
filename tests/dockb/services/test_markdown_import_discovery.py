"""Tests for _discover_chapter_files — how an import walk orders acts and chapters."""

from __future__ import annotations

import pytest

from dockb.services import markdown_import


class TestDiscoverChapterFiles:
    def test_orders_acts_by_number_with_roman_and_arabic_mixed(self, tmp_path):
        for name in ["Act 2", "Act IX", "Act 10", "Act I"]:
            act = tmp_path / name
            act.mkdir()
            (act / "Opening 1.md").write_text("x")
        assert [act for act, _ in markdown_import._discover_chapter_files(tmp_path)] == [
            "Act I",
            "Act 2",
            "Act IX",
            "Act 10",
        ]

    def test_roman_iii_before_iv(self, tmp_path):
        for name in ["Act IV", "Act III"]:
            act = tmp_path / name
            act.mkdir()
            (act / "Opening 1.md").write_text("x")
        assert [act for act, _ in markdown_import._discover_chapter_files(tmp_path)] == ["Act III", "Act IV"]

    def test_uppercase_unicode_roman_numerals_order_acts(self, tmp_path):
        for name in ["Act \u216b", "Act \u2163", "Act \u2164"]:  # XII 12, IV 4, V 5
            act = tmp_path / name
            act.mkdir()
            (act / "Opening 1.md").write_text("x")
        assert [act for act, _ in markdown_import._discover_chapter_files(tmp_path)] == [
            "Act \u2163",
            "Act \u2164",
            "Act \u216b",
        ]

    def test_lowercase_unicode_roman_numerals_order_acts(self, tmp_path):
        for name in ["Act \u217f", "Act \u217d", "Act \u217e"]:  # m 1000, c 100, d 500
            act = tmp_path / name
            act.mkdir()
            (act / "Opening 1.md").write_text("x")
        assert [act for act, _ in markdown_import._discover_chapter_files(tmp_path)] == [
            "Act \u217d",
            "Act \u217e",
            "Act \u217f",
        ]

    def test_unicode_and_ascii_roman_conflict_raises(self, tmp_path):
        (tmp_path / "Act IV").mkdir()
        (tmp_path / "Act \u2163").mkdir()  # Ⅳ = 4
        with pytest.raises(ValueError, match="both number as 4"):
            list(markdown_import._discover_chapter_files(tmp_path))

    def test_empty_act_none_sorts_first(self, tmp_path):
        (tmp_path / "Act None").mkdir()
        (tmp_path / "Act I").mkdir()
        (tmp_path / "Act None" / "Opening 1.md").write_text("x")
        (tmp_path / "Act I" / "Opening 1.md").write_text("x")
        assert [act for act, _ in markdown_import._discover_chapter_files(tmp_path)] == ["", "Act I"]

    def test_orders_chapters_by_trailing_number_then_letter(self, tmp_path):
        act = tmp_path / "Act I"
        act.mkdir()
        for name in ["Setup 5b.md", "Setup 10.md", "Opening 1.md", "Setup 5.md", "Setup 5a.md", "Setup 2.md"]:
            (act / name).write_text("x")
        assert [path.name for _, path in markdown_import._discover_chapter_files(tmp_path)] == [
            "Opening 1.md",
            "Setup 2.md",
            "Setup 5.md",
            "Setup 5a.md",
            "Setup 5b.md",
            "Setup 10.md",
        ]

    def test_embedded_number_flanked_by_spaces_orders_chapters(self, tmp_path):
        act = tmp_path / "Act I"
        act.mkdir()
        for name in [
            "Bad Guys Close In 49 Jael.md",
            "Bad Guys Close In 10 Jael.md",
            "Bad Guys Close In 48 Jael.md",
        ]:
            (act / name).write_text("x")
        assert [path.name for _, path in markdown_import._discover_chapter_files(tmp_path)] == [
            "Bad Guys Close In 10 Jael.md",
            "Bad Guys Close In 48 Jael.md",
            "Bad Guys Close In 49 Jael.md",
        ]

    def test_embedded_number_with_letter_suffix(self, tmp_path):
        act = tmp_path / "Act I"
        act.mkdir()
        for name in ["Bad Guys Close In 49 Jael.md", "Bad Guys Close In 48 Jael.md", "Bad Guys Close In 48b Jael.md"]:
            (act / name).write_text("x")
        assert [path.name for _, path in markdown_import._discover_chapter_files(tmp_path)] == [
            "Bad Guys Close In 48 Jael.md",
            "Bad Guys Close In 48b Jael.md",
            "Bad Guys Close In 49 Jael.md",
        ]

    def test_rightmost_number_wins_when_multiple_qualify(self, tmp_path):
        act = tmp_path / "Act I"
        act.mkdir()
        (act / "Bad 3 Guys Close In 48 Jael.md").write_text("x")
        (act / "Bad Guys Close In 47 Jael.md").write_text("x")
        assert [path.name for _, path in markdown_import._discover_chapter_files(tmp_path)] == [
            "Bad Guys Close In 47 Jael.md",
            "Bad 3 Guys Close In 48 Jael.md",
        ]

    def test_number_at_start_without_leading_space_raises(self, tmp_path):
        act = tmp_path / "Act I"
        act.mkdir()
        (act / "48 Jael.md").write_text("x")
        with pytest.raises(ValueError, match="not numbered"):
            list(markdown_import._discover_chapter_files(tmp_path))

    def test_files_in_nested_directories_under_an_act_are_chapters(self, tmp_path):
        nested = tmp_path / "Act I" / "deeper"
        nested.mkdir(parents=True)
        (nested / "Setup 3.md").write_text("x")
        assert [(act, path.name) for act, path in markdown_import._discover_chapter_files(tmp_path)] == [
            ("Act I", "Setup 3.md"),
        ]

    def test_unnumbered_chapter_file_raises(self, tmp_path):
        act = tmp_path / "Act I"
        act.mkdir()
        (act / "Notes.md").write_text("x")
        with pytest.raises(ValueError, match="not numbered"):
            list(markdown_import._discover_chapter_files(tmp_path))

    def test_multiple_letter_suffix_raises(self, tmp_path):
        act = tmp_path / "Act I"
        act.mkdir()
        (act / "Setup 5ab.md").write_text("x")
        with pytest.raises(ValueError, match="not numbered"):
            list(markdown_import._discover_chapter_files(tmp_path))

    def test_same_chapter_number_in_different_acts_ok(self, tmp_path):
        (tmp_path / "Act I").mkdir()
        (tmp_path / "Act II").mkdir()
        (tmp_path / "Act I" / "Opening 2.md").write_text("x")
        (tmp_path / "Act II" / "Opening 2.md").write_text("x")
        assert [(act, path.name) for act, path in markdown_import._discover_chapter_files(tmp_path)] == [
            ("Act I", "Opening 2.md"),
            ("Act II", "Opening 2.md"),
        ]

    def test_act_with_letter_suffix_raises(self, tmp_path):
        (tmp_path / "Act IVa").mkdir()
        with pytest.raises(ValueError, match="not numbered"):
            list(markdown_import._discover_chapter_files(tmp_path))

    def test_unparsable_act_name_raises(self, tmp_path):
        (tmp_path / "Act Foobar").mkdir()
        with pytest.raises(ValueError, match="not numbered"):
            list(markdown_import._discover_chapter_files(tmp_path))

    def test_acts_numbering_the_same_raise(self, tmp_path):
        (tmp_path / "Act 1").mkdir()
        (tmp_path / "Act I").mkdir()
        with pytest.raises(ValueError, match="both number as 1"):
            list(markdown_import._discover_chapter_files(tmp_path))

    def test_duplicate_chapter_sequence_in_one_act_raises(self, tmp_path):
        act = tmp_path / "Act I"
        act.mkdir()
        (act / "Opening 5.md").write_text("x")
        (act / "Setup 5.md").write_text("x")
        with pytest.raises(ValueError, match="Duplicate chapter"):
            list(markdown_import._discover_chapter_files(tmp_path))
