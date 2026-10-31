"""The chapter-title sequence number as a value rule.

A chapter title carries its position as a number with at most one trailing
letter — ``Setup 5b`` — sitting either at the end of the title or embedded
between spaces (``Bad Guys Close In 48 Jael``). Import orders files by it, and
renumbering rewrites it in place. The rule lives here, apart from the import
walker and the renumber service, because it is a property of the title rather
than of the layer that happens to use it: both must agree on where a title's
number sits.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_CHAPTER_NUMBER_RE = re.compile(r"(?<=\s)(\d+)([A-Za-z]?)(?=\s)|(\d+)([A-Za-z]?)$")


@dataclass(frozen=True)
class ChapterNumber:
    """A title's sequence number: its value, letter, and where it sits in the title."""

    number: int
    letter: str
    start: int
    end: int


def find_chapter_number(title: str) -> ChapterNumber | None:
    """Return the rightmost number in *title*, or None when it carries none."""
    matches = list(_CHAPTER_NUMBER_RE.finditer(title))
    if not matches:
        return None
    match = matches[-1]
    number, letter = match.group(1, 2)
    if number is None:
        number, letter = match.group(3, 4)
    assert number is not None
    return ChapterNumber(number=int(number), letter=letter or "", start=match.start(), end=match.end())


def renumber_title(title: str, number: int) -> str:
    """Return *title* with its sequence number replaced by *number*.

    The replacement occupies the same span as the old number, and any letter
    suffix is dropped. A title with no number gains one at the end.
    """
    found = find_chapter_number(title)
    if found is None:
        return f"{title} {number}"
    return f"{title[:found.start]}{number}{title[found.end :]}"
