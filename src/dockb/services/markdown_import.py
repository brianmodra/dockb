"""Apply a markdown chapter file's changes to the knowledge graph."""

from __future__ import annotations

import html
import logging
import uuid
from dataclasses import dataclass
from pathlib import Path

import yaml
from spacy.language import Language

from dockb.exceptions import ChapterMismatchError
from dockb.infrastructure.changes.detect_changes import (
    ChangedParagraph,
    ChapterDiff,
    NewParagraph,
    detect_changes,
)
from dockb.infrastructure.neo4j.unit_of_work_factory import UnitOfWorkFactory
from dockb.models.base import DataState
from dockb.models.chapter import Chapter
from dockb.models.document import Document
from dockb.models.paragraph import Paragraph
from dockb.models.sentence import Sentence
from dockb.models.utils.dockb_collection import InsertionMode
from dockb.repositories.chapter_repository import ChapterRepository
from dockb.repositories.document_repository import DocumentRepository

logger = logging.getLogger(__name__)

_METADATA_FILE = "document_metadata.yaml"


@dataclass
class ChapterImportSummary:
    """What a chapter-file import persisted."""

    chapter_id: str
    created: bool
    title: str = ""
    changed: int = 0
    added: int = 0
    deleted: int = 0


@dataclass
class DocumentMetadata:
    """The document's title and author, as located by the directory walker."""

    title: str
    author: str


def apply_chapter_file(
    document: Document,
    file_path: str | Path,
    nlp: Language,
    chapter_repo: ChapterRepository,
    uow_factory: UnitOfWorkFactory,
) -> ChapterImportSummary:
    """Persist the changes a markdown chapter file makes to *document*.

    Reads *file_path*, diffs it against the chapter it names through
    ``detect_changes``, validates that the named chapter belongs to *document*,
    rebuilds the chapter model from the diff, and persists the whole rebuilt
    chapter plus each changed/new paragraph's content in one unit-of-work
    commit. The chapter title is only ever set when the chapter is new. When
    anything changed, the new text — front matter and span-bearing body — is
    written back to *file_path*, so the file stays the graph's source of truth.
    """
    path = Path(file_path)
    content = path.read_text(encoding="utf-8")

    cached: dict[str, Chapter | None] = {}

    def load_once(chapter_id: str) -> Chapter | None:
        if chapter_id not in cached:
            cached[chapter_id] = chapter_repo.load(chapter_id)
        return cached[chapter_id]

    diff = detect_changes(
        content,
        nlp,
        get_chapter=load_once,
        create_chapter=_skeleton,
        title_fallback=path.stem,
    )
    chapter_id = diff.chapter_id

    if diff.created and diff.front_id is not None:
        raise ChapterMismatchError(f"Chapter '{diff.front_id}' from '{path}' is not a child of document '{document.id}'")
    if not diff.created and not any(c.id == chapter_id for c in document.chapters):
        raise ChapterMismatchError(f"Chapter '{chapter_id}' from '{path}' is not a child of document '{document.id}'")

    if not diff:
        if diff.created:
            chapter = _build_chapter(chapter_id, diff, None)
            _persist(uow_factory, document.id, chapter, [], [])
            _write_back_front_matter(path, ChapterImportSummary(chapter_id=chapter_id, created=True, title=diff.title))
        return ChapterImportSummary(chapter_id=chapter_id, created=diff.created)

    chapter = _build_chapter(chapter_id, diff, load_once(chapter_id))

    for paragraph_id in diff.deleted:
        chapter.delete_child(paragraph_id)

    changed_paragraphs = [_apply_changed(chapter, changed) for changed in diff.changed]
    added_paragraphs = _place_new_paragraphs(chapter, diff.new)

    _persist(uow_factory, document.id, chapter, changed_paragraphs, added_paragraphs)
    _write_back_chapter_file(path, chapter)

    return ChapterImportSummary(
        chapter_id=chapter.id,
        created=diff.created,
        title=diff.title,
        changed=len(changed_paragraphs),
        added=len(added_paragraphs),
        deleted=len(diff.deleted),
    )


def import_document_directory(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    document_dir: str | Path,
    user_name: str,
    nlp: Language,
    document_repo: DocumentRepository,
    chapter_repo: ChapterRepository,
    uow_factory: UnitOfWorkFactory,
) -> list[ChapterImportSummary]:
    """Import every chapter file under a document directory into its graph Document.

    Files are found recursively (``*.md`` anywhere beneath *document_dir*), in
    sorted order. The whole directory is imported into a single Document,
    resolved by its metadata (see ``_read_document_metadata``/``_resolve_document``),
    and one summary is returned per chapter file.
    """
    dir_path = Path(document_dir)
    if not dir_path.is_dir():
        raise ValueError(f"Document directory '{dir_path}' does not exist")
    metadata = _read_document_metadata(dir_path, user_name)
    document = _resolve_document(dir_path, metadata, document_repo, uow_factory)
    summaries = []
    for chapter_file in sorted(dir_path.rglob("*.md")):
        summary = apply_chapter_file(document, chapter_file, nlp, chapter_repo, uow_factory)
        summaries.append(summary)
    return summaries


def _write_back_chapter_file(chapter_file: Path, chapter: Chapter) -> None:
    """Rewrite *chapter_file* so its text mirrors *chapter*.

    The front matter keeps any existing attributes, adding the chapter's
    ``id``/``title``; the body is serialized from the rebuilt chapter as one
    identity span per sentence (mirroring ``SnapshotWriter``).
    """
    existing = chapter_file.read_text(encoding="utf-8")
    attrs = _load_front_matter_attrs(existing)
    attrs["id"] = chapter.id
    attrs["title"] = chapter.title
    front_matter = "---\n" + yaml.dump(attrs, default_flow_style=False, allow_unicode=True, sort_keys=False) + "---\n"
    body = _serialize_body(chapter)
    trailer = f"\n{body}\n" if body else ""
    chapter_file.write_text(front_matter + trailer, encoding="utf-8")


def _serialize_body(chapter: Chapter) -> str:
    """Serialize *chapter*'s paragraphs as id-spanned sentence lines, blank-line separated."""
    blocks = []
    for paragraph in chapter.paragraphs:
        lines = [
            f'<span data-par-id="{html.escape(paragraph.id, quote=True)}">{html.escape(sentence.get_text(), quote=True)}</span>'
            for sentence in paragraph.sentences
        ]
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)


def _write_back_front_matter(chapter_file: Path, summary: ChapterImportSummary) -> None:
    """Persist the new chapter's id/title in the file's front matter.

    A chapter that was just created (``summary.created``) has no file identity
    yet; its id is written into (or added to) the file's YAML front matter so
    later imports match it. Files that already carried a known id are untouched.
    """
    content = chapter_file.read_text(encoding="utf-8")
    chapter_file.write_text(_with_front_matter(content, summary.chapter_id, summary.title), encoding="utf-8")


def _front_matter_block(chapter_id: str, title: str) -> str:
    attrs: dict[str, object] = {"id": chapter_id, "title": title}
    return "---\n" + yaml.dump(attrs, default_flow_style=False, allow_unicode=True, sort_keys=False) + "---\n"


def _with_front_matter(content: str, chapter_id: str, title: str) -> str:
    """Return *content* with ``id``/``title`` merged into its front matter.

    A file with no opening ``---`` gets a front matter block prepended; one with
    an existing block keeps its other attributes, only ``id`` and ``title`` being
    added or overwritten.
    """
    if not content.startswith("---"):
        return _front_matter_block(chapter_id, title) + content
    attrs = _load_front_matter_attrs(content)
    attrs["id"] = chapter_id
    attrs["title"] = title
    merged = yaml.dump(attrs, default_flow_style=False, allow_unicode=True, sort_keys=False)
    lines = content.splitlines(keepends=True)
    closing = next((index for index in range(1, len(lines)) if lines[index].startswith("---")), None)
    if closing is None:
        raise ChapterMismatchError("Snapshot file is missing closing '---' for front matter")
    body = "".join(lines[closing + 1 :])
    return "---\n" + merged + "---\n" + body


def _load_front_matter_attrs(content: str) -> dict[str, object]:
    """Return the front-matter attributes of *content*, empty when none are present."""
    if not content.startswith("---"):
        return {}
    lines = content.splitlines(keepends=True)
    closing = next((index for index in range(1, len(lines)) if lines[index].startswith("---")), None)
    if closing is None:
        raise ChapterMismatchError("Snapshot file is missing closing '---' for front matter")
    attrs = yaml.safe_load("".join(lines[1:closing])) or {}
    if not isinstance(attrs, dict):
        raise ChapterMismatchError("Front matter must be a mapping of key: value pairs")
    return dict(attrs)


def _read_document_metadata(document_dir: Path, user_name: str) -> DocumentMetadata:
    """Read a document directory's metadata, defaulting the missing fields.

    ``title`` defaults to the directory name, ``author`` to *user_name* when
    ``document_metadata.yaml`` is absent or does not carry the field.
    """
    attrs: dict[str, object] = {}
    metadata_path = document_dir / _METADATA_FILE
    if metadata_path.is_file():
        parsed = yaml.safe_load(metadata_path.read_text(encoding="utf-8"))
        if isinstance(parsed, dict):
            attrs = parsed
    return DocumentMetadata(
        title=str(attrs.get("title") or document_dir.name),
        author=str(attrs.get("author") or user_name),
    )


def _resolve_document(
    document_dir: Path,
    metadata: DocumentMetadata,
    document_repo: DocumentRepository,
    uow_factory: UnitOfWorkFactory,
) -> Document:
    """Return the graph Document for a document directory, creating it if missing.

    An existing Document is matched by exact title and reused; a directory whose
    title no Document answers for is turned into a fresh NEW Document and
    persisted immediately, so later chapter imports can link to it.
    """
    matches = [row for row in document_repo.list_all() if row["title"] == metadata.title]
    if matches:
        if len(matches) > 1:
            logger.warning("Multiple documents titled %r; reusing %r", metadata.title, matches[0]["id"])
        document = document_repo.load(matches[0]["id"])
        if document is not None:
            return document
        logger.warning("Document %r listed but could not be loaded", matches[0]["id"])
    document = Document(title=metadata.title, author=metadata.author, state=DataState.NEW)
    uow = uow_factory.get_unit_of_work()
    uow.register(document)
    uow.commit()
    _write_document_metadata(document_dir, metadata)
    logger.debug("Persisted new document %r under %s", document.id, document_dir)
    return document


def _write_document_metadata(document_dir: Path, metadata: DocumentMetadata) -> None:
    """Record the resolved ``title``/``author`` in the directory's metadata file.

    Existing attributes are preserved; only the two fields are set. This keeps
    the values the import derived (the directory name and current user, say)
    explicit in the file for the next run.
    """
    attrs: dict[str, object] = {}
    metadata_path = document_dir / _METADATA_FILE
    if metadata_path.is_file():
        parsed = yaml.safe_load(metadata_path.read_text(encoding="utf-8"))
        if isinstance(parsed, dict):
            attrs = dict(parsed)
    attrs["title"] = metadata.title
    attrs["author"] = metadata.author
    metadata_path.write_text(
        yaml.dump(attrs, default_flow_style=False, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )


def _persist(
    uow_factory: UnitOfWorkFactory,
    document_id: str,
    chapter: Chapter,
    changed_paragraphs: list[Paragraph],
    added_paragraphs: list[Paragraph],
) -> None:
    """Register the rebuilt chapter and its content-bearing paragraphs, then commit once."""
    uow = uow_factory.get_unit_of_work()
    uow.register(chapter, document_id=document_id)
    for paragraph in changed_paragraphs + added_paragraphs:
        uow.register(paragraph, chapter_id=chapter.id)
    uow.commit()


def _build_chapter(chapter_id: str, diff: ChapterDiff, loaded: Chapter | None) -> Chapter:
    """Return the NEW chapter skeleton, or the already-loaded old chapter marked CHANGED."""
    if diff.created:
        return Chapter(id=chapter_id, title=diff.title, state=DataState.NEW)
    if loaded is None:
        raise ChapterMismatchError(f"Chapter '{chapter_id}' was not found in the knowledge graph")
    loaded.state = DataState.CHANGED
    return loaded


def _skeleton(front_id: str | None, title: str) -> Chapter:
    """Build the empty chapter side for detect_changes when no old chapter exists."""
    return Chapter(id=front_id or str(uuid.uuid4()), title=title)


def _build_paragraph(new: NewParagraph) -> Paragraph:
    """Build a fresh NEW paragraph with a Sentence per ``new.sentence_texts`` entry."""
    paragraph = Paragraph()
    for text in new.sentence_texts:
        paragraph.append_child(Sentence(text=text))
    paragraph.state = DataState.NEW
    return paragraph


def _apply_changed(chapter: Chapter, changed: ChangedParagraph) -> Paragraph:
    """Replace *changed* paragraph's sentences and mark it CHANGED for persistence."""
    paragraph = next(p for p in chapter.paragraphs if p.id == changed.par_id)
    paragraph.sentences[:] = [Sentence(text=text) for text in changed.sentence_texts]
    paragraph.state = DataState.CHANGED
    return paragraph


def _place_new_paragraphs(chapter: Chapter, new_paragraphs: list[NewParagraph]) -> list[Paragraph]:
    """Insert every new paragraph and return them, in file order.

    Consecutive new paragraphs (same ``after_id``, or both ``at_start``) keep
    their file order by being placed after the previous placed paragraph;
    otherwise ``after_id``/``at_start``/append decide the position.
    """
    placed: list[Paragraph] = []
    previous_new: NewParagraph | None = None
    previous_placed: Paragraph | None = None
    for new in new_paragraphs:
        paragraph = _build_paragraph(new)
        consecutive = (
            previous_new is not None
            and previous_placed is not None
            and (new.after_id == previous_new.after_id or (new.at_start and previous_new.at_start))
        )
        if consecutive and previous_placed is not None:
            chapter.insert_child(paragraph, InsertionMode.AFTER, after=previous_placed.id)
        elif new.after_id is not None:
            chapter.insert_child(paragraph, InsertionMode.AFTER, after=new.after_id)
        elif new.at_start:
            chapter.insert_child(paragraph, InsertionMode.FIRST)
        else:
            chapter.insert_child(paragraph, InsertionMode.LAST)
        placed.append(paragraph)
        previous_new, previous_placed = new, paragraph
    return placed
