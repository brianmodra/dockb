"""Planning a document's chapter renumber: the titles, checked before anything writes."""

from __future__ import annotations

from dockb.chapter_numbers import renumber_title
from dockb.exceptions import DuplicateTitleError
from dockb.infrastructure.document_store.store import ChapterRename


def row_category(row: dict[str, str | int]) -> str:
    """Return a list-row's category, defaulting old rows to ``Chapter``."""
    return str(row.get("category") or "Chapter")


def plan_renumber(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    rows: list[dict[str, str | int]],
    start: int = 1,
) -> tuple[list[dict[str, str]], list[dict[str, str]], list[ChapterRename]]:
    """Plan a document's renumber from its chapter rows in display order.

    Act chapters (category ``Chapter``) take their position as the new number,
    counting from *start*; ``Character`` rows are untouched. A case-insensitive
    duplicate among the final titles — new act titles beside unchanged character
    titles — raises ``DuplicateTitleError`` before anything is written. Returns
    the graph retitle entries, the ``{id, old_title, new_title}`` reports, and
    the store moves, all covering only the chapters whose title changes.
    """
    numbered = [row for row in rows if row_category(row) != "Character"]
    characters = [row for row in rows if row_category(row) == "Character"]
    new_titles = {str(row["id"]): renumber_title(str(row["title"]), position) for position, row in enumerate(numbered, start=start)}
    final_titles = [new_titles[str(row["id"])] for row in numbered] + [str(row["title"]) for row in characters]
    seen: set[str] = set()
    for title in final_titles:
        if title.lower() in seen:
            raise DuplicateTitleError(title)
        seen.add(title.lower())
    entries: list[dict[str, str]] = []
    renames: list[dict[str, str]] = []
    moves: list[ChapterRename] = []
    for row in numbered:
        chapter_id = str(row["id"])
        old_title = str(row["title"])
        new_title = new_titles[chapter_id]
        if new_title == old_title:
            continue
        entries.append({"id": chapter_id, "title": new_title})
        renames.append({"id": chapter_id, "old_title": old_title, "new_title": new_title})
        moves.append(
            ChapterRename(
                act=str(row.get("act") or ""),
                category=row_category(row),
                old_title=old_title,
                new_title=new_title,
            )
        )
    return entries, renames, moves
