"""Chapter front-matter reconciliation: character properties and the POV.

The chapter file's YAML front matter is the hand-maintained source for who a
character is and whose point of view a chapter is written from; the graph
mirrors it. These helpers learn what a saved file's front matter says into a
chapter model, write the model back into the file, and set or clear a chapter's
POV character — the POV living as a character chapter's **id** in the graph but
its **title** in the file.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from dockb.infrastructure.markdown import front_matter
from dockb.infrastructure.markdown import writer as markdown_writer
from dockb.models.base import DataState
from dockb.models.chapter import Chapter

if TYPE_CHECKING:
    from spacy.language import Language

    from dockb.infrastructure.document_store.store import DocumentStore
    from dockb.infrastructure.neo4j.unit_of_work_factory import UnitOfWorkFactory
    from dockb.repositories.chapter_repository import ChapterRepository
    from dockb.services.markdown_import import ChapterDiff

__all__ = [
    "apply_character_props",
    "apply_pov",
    "character_props_changed",
    "merge_pov_front_matter",
    "reconcile_pov",
    "reconcile_pov_title",
    "set_pov",
    "write_back_chapter_file",
]


def apply_character_props(chapter: Chapter, diff: ChapterDiff) -> None:
    """Write the file's character properties onto *chapter*.

    The front matter is the hand-maintained source, so when the chapter is a
    Character (or the file carries any of the properties) the graph values are
    replaced wholesale — including a property the hand edit dropped, which
    clears. A manuscript chapter whose file carries none of them is untouched,
    keeping the graph's empties.
    """
    carried = any(
        (
            diff.first_name,
            diff.surname,
            diff.middle_names,
            diff.nicknames,
            diff.age is not None,
            diff.location,
        )
    )
    if not carried and chapter.category != "Character":
        return
    chapter.first_name = diff.first_name
    chapter.surname = diff.surname
    chapter.middle_names = list(diff.middle_names)
    chapter.nicknames = list(diff.nicknames)
    chapter.age = diff.age
    chapter.location = diff.location


def character_props_changed(diff: ChapterDiff, chapter: Chapter) -> bool:
    """Return whether the file's character properties differ from the graph's."""
    return (
        diff.first_name != chapter.first_name
        or diff.surname != chapter.surname
        or list(diff.middle_names) != list(chapter.middle_names)
        or list(diff.nicknames) != list(chapter.nicknames)
        or diff.age != chapter.age
        or diff.location != chapter.location
    )


def reconcile_pov(
    chapter: Chapter,
    diff: ChapterDiff,
    document_id: str,
    chapter_repo: ChapterRepository,
    owner: str,
) -> tuple[list[str], bool]:
    """Align *chapter*'s `pov` with the file's front matter, and report warnings.

    The front matter carries the POV character's **title**; the graph carries
    its **id**. A title that names a Character chapter of the same document sets
    the id (the file is the hand-edited source); a title that names nothing
    warns and leaves the stored id alone; a key that is absent or empty is no
    POV at all and clears the id. A stored id that no longer resolves (the
    character chapter was deleted) warns every time it is seen — the write-back
    writes no pov line for it, so the next save's absent key clears the id.
    Returns the warnings and whether the chapter's `pov` changed.
    """
    before = chapter.pov
    warnings: list[str] = []
    if diff.pov is None or diff.pov == "":
        chapter.pov = ""
    else:
        resolved = chapter_repo.find_character_id_by_title(document_id, diff.pov, owner)
        if resolved is not None:
            chapter.pov = resolved
        else:
            warnings.append(
                f"The pov '{diff.pov}' did not match any character chapter of this document; the chapter's stored POV is unchanged"
            )
    if chapter.pov and chapter_repo.find_character_title(document_id, chapter.pov, owner) is None:
        warnings.append("The chapter's POV character no longer exists; the pov line is removed and will be cleared on the next save")
    return warnings, chapter.pov != before


def reconcile_pov_title(chapter: Chapter, document_id: str, chapter_repo: ChapterRepository, owner: str) -> str:
    """The POV character's **title** for the front matter ("" when there is no POV)."""
    if not chapter.pov:
        return ""
    return chapter_repo.find_character_title(document_id, chapter.pov, owner) or ""


def write_back_chapter_file(
    chapter_file: Path,
    chapter: Chapter,
    nlp: Language | None,
    pov_title: str | None = None,
) -> None:
    """Rewrite *chapter_file* so its text mirrors *chapter*.

    The front matter keeps any existing attributes, adding the chapter's
    ``id``/``title`` (and its ``act``/``category`` when set); the body is the
    chapter serialized as one identity span per paragraph. *pov_title* — when
    not None — is the chapter's POV character's title: a non-empty value is
    written as the ``pov`` line, an empty one removes the line, which is how a
    dangling POV (or a cleared one) empties out of the file. Left as None the
    file's own pov line is untouched.
    """
    existing = chapter_file.read_text(encoding="utf-8")
    attrs, _body = front_matter.parse(existing)
    attrs["id"] = chapter.id
    attrs["title"] = chapter.title
    if chapter.act:
        attrs["act"] = chapter.act
    attrs["category"] = chapter.category
    attrs.update(markdown_writer.character_front_matter(chapter))
    if pov_title is not None:
        if pov_title:
            attrs["pov"] = pov_title
        else:
            attrs.pop("pov", None)
    chapter_file.write_text(markdown_writer.render_chapter_markdown(chapter, nlp, attrs=attrs), encoding="utf-8")


def set_pov(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    chapter: Chapter,
    document_id: str,
    name: str,
    *,
    chapter_repo: ChapterRepository,
    uow_factory: UnitOfWorkFactory,
    store: DocumentStore | None,
    document: object | None,
    owner: str,
) -> dict[str, object]:
    """Set, suggest, or clear the chapter's point-of-view character.

    An empty *name* clears the POV. A name that matches a Character chapter
    of the chapter's own document applies it: the graph stores the
    character chapter's **id**, the file's front matter its **title**. A
    name that matches nothing but sits inside some character's name (at
    least three characters) is not applied — the answer carries the
    suggestion, so the caller can offer it; a name with no match at all
    answers a warning. In neither case does the graph change.
    """
    typed = name.strip()
    if not typed:
        return apply_pov(chapter, document_id, None, uow_factory=uow_factory, store=store, document=document, owner=owner)
    match = chapter_repo.find_character_by_name(document_id, typed.split(), owner)
    if match is not None:
        return apply_pov(chapter, document_id, match, uow_factory=uow_factory, store=store, document=document, owner=owner)
    suggestion: dict[str, str] | None = None
    if len(typed) >= 3:
        found = chapter_repo.find_characters_containing(document_id, typed, owner)
        suggestion = found[0] if found else None
    if suggestion is not None:
        warning = f'The pov "{typed}" did not match any character chapter; ' f'perhaps you meant "{suggestion["title"]}"'
    else:
        warning = f'The pov "{typed}" did not match any character chapter'
    return {"applied": False, "pov": None, "warning": warning}


def apply_pov(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    chapter: Chapter,
    document_id: str,
    match: dict[str, str] | None,
    *,
    uow_factory: UnitOfWorkFactory,
    store: DocumentStore | None,
    document: object | None,
    owner: str,
) -> dict[str, object]:
    """Persist a POV set (to *match*) or clear (None) on graph and file.

    The graph stores the character chapter's id in one unit-of-work commit;
    the file's front matter gains (or loses) the pov line, committed to the
    document's git. The answer says what the chapter's POV now is.
    """
    chapter.pov = match["id"] if match else ""
    chapter.state = DataState.CHANGED
    uow = uow_factory.get_unit_of_work()
    uow.register(chapter, document_id=document_id, owner=owner)
    uow.commit()
    if store is not None and document is not None:
        merge_pov_front_matter(store, document, chapter, match["title"] if match else None)
    return {
        "applied": True,
        "pov": {"id": match["id"], "title": match["title"]} if match else None,
        "warning": None,
    }


def merge_pov_front_matter(
    store: DocumentStore,
    document: object,
    chapter: Chapter,
    pov_title: str | None,
) -> None:
    """Write the pov line into the chapter's owned file: the title, or nothing."""
    document_title = getattr(document, "title", "")
    content = store.read_chapter(document_title, chapter.act, chapter.title, chapter.category)
    if content is None:
        return
    if pov_title:
        merged = front_matter.merge(content, {"pov": pov_title})
    else:
        attrs, body = front_matter.parse(content)
        attrs.pop("pov", None)
        merged = front_matter.render(attrs) + ("\n" + body if body else "")
    store.write_chapter(document_title, chapter.act, chapter.title, merged, chapter.category)
    store.git_commit(document_title, f"pov: chapter {chapter.id[:8]}")
