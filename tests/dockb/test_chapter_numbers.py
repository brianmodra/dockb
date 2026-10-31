"""The chapter-title sequence number rule."""

import pytest

from dockb.chapter_numbers import find_chapter_number, renumber_title


@pytest.mark.parametrize(
    ("title", "number", "letter"),
    [
        ("Opening 1", 1, ""),
        ("Setup 5b", 5, "b"),
        ("Prologue 0", 0, ""),
        ("Bad Guys Close In 48 Jael", 48, ""),
        ("Debate Break in 16b", 16, "b"),
        ("Fun & Games 35", 35, ""),
        ("Executing The Plan 68b", 68, "b"),
        ("Act 3 Scene 5", 5, ""),
    ],
)
def test_finds_the_rightmost_number_and_its_letter(title: str, number: int, letter: str) -> None:
    found = find_chapter_number(title)
    assert found is not None
    assert found.number == number
    assert found.letter == letter


def test_finds_the_number_where_it_sits_in_the_title() -> None:
    found = find_chapter_number("Bad Guys Close In 48 Jael")
    assert found is not None
    assert "Bad Guys Close In 48 Jael"[found.start : found.end] == "48"


def test_a_title_without_a_number_finds_none() -> None:
    assert find_chapter_number("Veronica") is None


@pytest.mark.parametrize(
    ("title", "number", "expected"),
    [
        ("Opening 1", 1, "Opening 1"),
        ("Opening 4", 1, "Opening 1"),
        ("Setup 5b", 3, "Setup 3"),
        ("Prologue 0", 1, "Prologue 1"),
        ("Bad Guys Close In 48 Jael", 7, "Bad Guys Close In 7 Jael"),
        ("Executing The Plan 68b", 5, "Executing The Plan 5"),
        ("Veronica", 3, "Veronica 3"),
        ("Act 3 Scene 5", 9, "Act 3 Scene 9"),
    ],
)
def test_renumbering_keeps_the_number_in_its_space(title: str, number: int, expected: str) -> None:
    assert renumber_title(title, number) == expected


def test_renumbering_is_idempotent_for_the_same_number() -> None:
    assert renumber_title("Opening 1", 1) == "Opening 1"
