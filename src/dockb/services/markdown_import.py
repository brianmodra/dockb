"""Apply a markdown chapter file's changes to the knowledge graph."""

from __future__ import annotations

import logging
import re
import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import yaml
from spacy.language import Language

from dockb.exceptions import ChapterMismatchError, DocumentFormatError
from dockb.infrastructure.changes.detect_changes import (
    ChangedParagraph,
    ChapterDiff,
    NewParagraph,
    detect_changes,
)
from dockb.infrastructure.document_store.store import DocumentMetadata
from dockb.infrastructure.markdown import front_matter, writer
from dockb.infrastructure.neo4j.unit_of_work_factory import UnitOfWorkFactory
from dockb.models.base import DataState
from dockb.models.chapter import Chapter
from dockb.models.document import Document
from dockb.models.paragraph import Paragraph
from dockb.models.sentence import Sentence
from dockb.models.utils.dockb_collection import InsertionMode
from dockb.repositories.chapter_repository import ChapterRepository
from dockb.repositories.document_repository import DocumentRepository
from dockb.services.semantics.doc_cache import DocCache
from dockb.services.semantics.sentence_tokenizer import SentenceTokenizer
from dockb.timing import measure

logger = logging.getLogger(__name__)

_METADATA_FILE = "document_metadata.yaml"


@dataclass
class ChapterImportSummary:
    """What a chapter-file import persisted."""

    chapter_id: str
    created: bool
    title: str = ""
    category: str = ""
    changed: int = 0
    added: int = 0
    deleted: int = 0


def apply_chapter_file(  # pylint: disable=too-many-arguments,too-many-positional-arguments,too-many-locals
    document: Document,
    file_path: str | Path,
    nlp: Language,
    chapter_repo: ChapterRepository,
    uow_factory: UnitOfWorkFactory,
    single_newline_paragraphs: bool = False,
    act: str | None = None,
    category: Literal["Chapter", "Character"] | None = None,
    write_back: bool = True,
) -> ChapterImportSummary:
    """Persist the changes a markdown chapter file makes to *document*.

    Reads *file_path*, diffs it against the chapter it names through
    ``detect_changes``, validates that the named chapter belongs to *document*,
    rebuilds the chapter model from the diff, and persists the whole rebuilt
    chapter plus each changed/new paragraph's content in one unit-of-work
    commit. The chapter title is only ever set when the chapter is new. When
    anything changed, the new text — front matter and span-bearing body — is
    written back to *file_path*, so the file stays the graph's source of truth.
    An *act* override (from the containing directory) wins over both the
    front matter and the graph value, so the tree's placement is authoritative.
    A *category* override (from the ``Characters`` directory) likewise wins
    over the front matter; without it a new chapter keeps its front-matter
    ``category`` (defaulting to ``Chapter``) and an existing chapter keeps the
    graph's value. With ``single_newline_paragraphs`` a line is a paragraph and sentences run
    on inside it (see ``detect_changes``); the write-back is always canonical.
    With ``write_back`` disabled the source file is left byte-for-byte
    unchanged (no front matter, no canonical rewrite); the graph is still
    updated, and a later import has no front-matter id to match, so it assigns
    a fresh id to the file on every run.
    """
    path = Path(file_path)
    with measure("stage.parse_file"):
        content = path.read_text(encoding="utf-8")

        cached: dict[str, Chapter | None] = {}

        def load_once(chapter_id: str) -> Chapter | None:
            if chapter_id not in cached:
                cached[chapter_id] = chapter_repo.load(chapter_id)
            return cached[chapter_id]

        diff = detect_changes(
            content,
            get_chapter=load_once,
            create_chapter=_skeleton,
            title_fallback=path.stem,
            single_newline_paragraphs=single_newline_paragraphs,
        )
    chapter_id = diff.chapter_id

    if diff.created and diff.front_id is not None:
        raise ChapterMismatchError(f"Chapter '{diff.front_id}' from '{path}' is not a child of document '{document.id}'")
    if not diff.created and not any(c.id == chapter_id for c in document.chapters):
        raise ChapterMismatchError(f"Chapter '{chapter_id}' from '{path}' is not a child of document '{document.id}'")

    if not diff:
        if diff.created:
            chapter = _build_chapter(chapter_id, diff, None)
            if act is not None:
                chapter.act = act
            if category is not None:
                chapter.category = category
            with measure("stage.persist"):
                _persist(uow_factory, document.id, chapter, [], [], nlp)
            if write_back:
                _write_back_front_matter(
                    path,
                    ChapterImportSummary(
                        chapter_id=chapter_id,
                        created=True,
                        title=diff.title,
                        category=category or "",
                    ),
                )
        return ChapterImportSummary(
            chapter_id=chapter_id,
            created=diff.created,
            title=diff.title,
            category=_resolved_category(diff, category, load_once(chapter_id)),
        )

    chapter = _build_chapter(chapter_id, diff, load_once(chapter_id))
    if act is not None:
        chapter.act = act
    if category is not None:
        chapter.category = category

    for paragraph_id in diff.deleted:
        chapter.delete_child(paragraph_id)

    with measure("stage.spacy"):
        changed_paragraphs = [_apply_changed(chapter, changed, nlp) for changed in diff.changed]
        added_paragraphs = _place_new_paragraphs(chapter, diff.new, nlp)

    with measure("stage.persist"):
        _persist(uow_factory, document.id, chapter, changed_paragraphs, added_paragraphs, nlp)
    if write_back:
        with measure("stage.render"):
            _write_back_chapter_file(path, chapter, nlp)

    return ChapterImportSummary(
        chapter_id=chapter.id,
        created=diff.created,
        title=diff.title,
        category=chapter.category,
        changed=len(changed_paragraphs),
        added=len(added_paragraphs),
        deleted=len(diff.deleted),
    )


def _resolved_category(diff: ChapterDiff, override: str | None, loaded: Chapter | None) -> str:
    """Return the category a summary reports for a file whose diff is empty.

    A file with nothing to change never builds a chapter model, so the summary
    has to work the same precedence out from the diff, the directory override
    and the graph: the override wins, then the file's own front matter, then
    what the chapter already is, and ``Chapter`` where none of those say.
    """
    if override is not None:
        return override
    if diff.category:
        return diff.category
    return (loaded.category if loaded is not None else "") or "Chapter"


def import_document_directory(  # pylint: disable=too-many-arguments,too-many-positional-arguments,too-many-locals
    document_dir: str | Path,
    user_name: str,
    nlp: Language,
    document_repo: DocumentRepository,
    chapter_repo: ChapterRepository,
    uow_factory: UnitOfWorkFactory,
    single_newline_paragraphs: bool = False,
    write_back: bool = True,
) -> list[ChapterImportSummary]:
    """Import every chapter file under a document directory into its graph Document.

    Chapters live inside top-level ``Act <name>`` subdirectories or the
    reserved ``Characters`` directory (see ``_discover_chapter_files``): each
    file is imported with the act its directory names (``Characters`` files
    carry no act), so placement is authoritative over the file's front matter.
    Root-level files and other non-act directories hold no chapters and are
    skipped. Acts are processed by the number their name carries (digits or
    Roman numerals, ``Act None`` first), then ``Characters`` last. Act files
    run by their sequence number with optional letter, trailing
    at the end of or embedded between spaces in the name (5, 5a, 5b, 6; "Bad
    Guys Close In 48 Jael" → 48) — an act file's name must carry that
    number; ``Characters`` files need no number and run by file name, each new
    chapter following the previous file into the graph. The whole directory is
    imported into a single Document, resolved by its metadata (see
    ``_read_document_metadata``/``_resolve_document``), and one summary is
    returned per chapter file. An unparsable act name, an unnumbered act
    file, or two acts or two act files numbering the same abort the import.
    ``single_newline_paragraphs`` is forwarded to every ``apply_chapter_file``
    call; ``write_back`` is forwarded to both the document resolution (its
    metadata write-back) and every chapter apply.
    """
    dir_path = Path(document_dir)
    if not dir_path.is_dir():
        raise DocumentFormatError(f"Document directory '{dir_path}' does not exist")
    metadata = _read_document_metadata(dir_path, user_name)
    document = _resolve_document(dir_path, metadata, document_repo, uow_factory, write_back=write_back)
    summaries = []
    for act, category, chapter_file in _discover_chapter_files(dir_path):
        summary = apply_chapter_file(
            document,
            chapter_file,
            nlp,
            chapter_repo,
            uow_factory,
            single_newline_paragraphs=single_newline_paragraphs,
            act=act,
            category=category,
            write_back=write_back,
        )
        summaries.append(summary)
    if summaries:
        chapter_repo.reorder(document.id, [s.chapter_id for s in summaries])
    return summaries


_CHAPTER_SEQUENCE_RE = re.compile(r"(?<=\s)(\d+)([A-Za-z]?)(?=\s)|(\d+)([A-Za-z]?)$")
_ROMAN_RE = re.compile(r"M{0,3}(?:CM|CD|D?C{0,3})(?:XC|XL|L?X{0,3})(?:IX|IV|V?I{0,3})")
_ROMAN_DIGITS = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100, "D": 500, "M": 1000}
_UNICODE_ROMAN = str.maketrans(
    {
        "\u2160": "I",
        "\u2161": "II",
        "\u2162": "III",
        "\u2163": "IV",
        "\u2164": "V",
        "\u2165": "VI",
        "\u2166": "VII",
        "\u2167": "VIII",
        "\u2168": "IX",
        "\u2169": "X",
        "\u216a": "XI",
        "\u216b": "XII",
        "\u216c": "L",
        "\u216d": "C",
        "\u216e": "D",
        "\u216f": "M",
        "\u2170": "i",
        "\u2171": "ii",
        "\u2172": "iii",
        "\u2173": "iv",
        "\u2174": "v",
        "\u2175": "vi",
        "\u2176": "vii",
        "\u2177": "viii",
        "\u2178": "ix",
        "\u2179": "x",
        "\u217a": "xi",
        "\u217b": "xii",
        "\u217c": "l",
        "\u217d": "c",
        "\u217e": "d",
        "\u217f": "m",
    }
)


def _roman_to_int(value: str) -> int | None:
    """Return *value* as an int when it is a strict canonical Roman numeral, else None.

    The single-character Unicode Roman numerals (U+2160–U+216F and
    U+2170–U+217F) translate to their ASCII letters first, so ``Ⅳ`` and ``IV``
    are the same act number.
    """
    text = value.translate(_UNICODE_ROMAN).upper()
    if not _ROMAN_RE.fullmatch(text):
        return None
    total = 0
    previous = 0
    for char in reversed(text):
        digit = _ROMAN_DIGITS[char]
        total += -digit if digit < previous else digit
        previous = digit
    return total


def _parse_act_directory(subdir: Path) -> tuple[int, str]:
    """Return ``(number, act)`` for an ``Act <name>`` directory.

    The name after the ``Act `` prefix must be digits or a strict Roman
    numeral, whose value orders the act. The reserved ``Act None`` is the
    empty act: number 0, sorting before every numbered act. Any other name —
    a letter suffix, free text, an empty label — raises DocumentFormatError,
    because a chapter must sit in a numbered act.
    """
    label = subdir.name[len("Act ") :]
    if label == "None":
        return 0, ""
    number = int(label) if label.isascii() and label.isdigit() else _roman_to_int(label)
    if number is None:
        raise DocumentFormatError(f"Act directory '{subdir.name}' is not numbered with digits or Roman numerals")
    return number, subdir.name


def _chapter_sort_key(file_path: Path) -> tuple[int, str]:
    """Return the ``(number, letter)`` ordering key for a chapter file.

    The sequence number is the rightmost digits in the stem carrying at most
    one trailing letter, sitting either at the end of the name (``Opening 5``
    → ``(5, '')``, ``Setup 5b`` → ``(5, 'b')``) or embedded and flanked by
    spaces (``Bad Guys Close In 48 Jael`` → ``(48, '')``). A stem with no
    such number is not a numbered chapter and raises DocumentFormatError.
    """
    matches = list(_CHAPTER_SEQUENCE_RE.finditer(file_path.stem))
    if not matches:
        raise DocumentFormatError(f"Chapter file '{file_path}' is not numbered")
    match = matches[-1]
    number, letter = match.group(1, 2)
    if number is None:
        number, letter = match.group(3, 4)
    return int(number), (letter or "").lower()


_CHARACTERS_DIR = "Characters"


def _discover_chapter_files(document_dir: Path) -> Iterator[tuple[str, Literal["Chapter", "Character"], Path]]:
    """Yield ``(act, category, file)`` for every chapter file under *document_dir*.

    Chapters exist inside top-level ``Act <name>`` directories, whose
    name must number the act as digits or a strict Roman numeral (``Act
    None`` is the empty act), and inside the reserved ``Characters``
    directory, whose files are category ``Character`` with no act. Act
    chapters import in act value order, then each file's sequence number
    with its optional letter, trailing at the end of or embedded between
    spaces in the name (5, 5a, 5b, 6; "Bad Guys Close In 48
    Jael" → 48) — an act chapter's file name must carry that number.
    ``Characters`` files need no number: they import after the acts in
    file-name order, whatever their name says.
    Anything else — a root-level or non-act file, a non-``Characters``
    directory, an unparsable act name, two act files in one act numbering
    the same, or two acts numbering the same — raises DocumentFormatError.
    """
    acts: list[tuple[tuple[int, str], Path]] = [
        (_parse_act_directory(subdir), subdir) for subdir in document_dir.iterdir() if subdir.is_dir() and subdir.name.startswith("Act ")
    ]
    acts.sort(key=lambda pair: pair[0])
    previous: tuple[int, str] | None = None
    for (number, act), subdir in acts:
        if previous is not None:
            if previous[0] == number:
                raise DocumentFormatError(f"Acts '{previous[1]}' and '{subdir.name}' both number as {number}")
        previous = (number, subdir.name)
        chapters = sorted(
            ((_chapter_sort_key(file_path), file_path) for file_path in subdir.rglob("*.md")),
            key=lambda pair: pair[0],
        )
        last_key: tuple[int, str] | None = None
        for key, chapter_file in chapters:
            if key == last_key:
                raise DocumentFormatError(f"Duplicate chapter number '{chapter_file.stem}' in '{subdir.name}'")
            last_key = key
            yield act, "Chapter", chapter_file

    characters_dir = document_dir / _CHARACTERS_DIR
    if characters_dir.is_dir():
        character_files = sorted(
            (file_path for file_path in characters_dir.rglob("*.md")),
            key=lambda file_path: (file_path.name, str(file_path)),
        )
        for chapter_file in character_files:
            yield "", "Character", chapter_file


def _write_back_chapter_file(chapter_file: Path, chapter: Chapter, nlp: Language) -> None:
    """Rewrite *chapter_file* so its text mirrors *chapter*.

    The front matter keeps any existing attributes, adding the chapter's
    ``id``/``title`` (and its ``act``/``category`` when set); the body is the
    chapter serialized as one identity span per paragraph.
    """
    existing = chapter_file.read_text(encoding="utf-8")
    attrs = front_matter.parse(existing)[0]
    attrs["id"] = chapter.id
    attrs["title"] = chapter.title
    if chapter.act:
        attrs["act"] = chapter.act
    attrs["category"] = chapter.category
    chapter_file.write_text(writer.render_chapter_markdown(chapter, nlp, attrs=attrs), encoding="utf-8")


def _write_back_front_matter(chapter_file: Path, summary: ChapterImportSummary) -> None:
    """Persist the new chapter's id/title (and directory category) in the file's front matter.

    A chapter that was just created (``summary.created``) has no file identity
    yet; its id is written into (or added to) the file's YAML front matter so
    later imports match it. Files that already carried a known id are untouched.
    A non-empty ``summary.category`` (the ``Characters`` directory override) is
    recorded too, so the file says what category it belongs to.
    """
    content = chapter_file.read_text(encoding="utf-8")
    updates = {"id": summary.chapter_id, "title": summary.title}
    if summary.category:
        updates["category"] = summary.category
    chapter_file.write_text(front_matter.merge(content, updates), encoding="utf-8")


def _read_document_metadata(document_dir: Path, user_name: str) -> DocumentMetadata:
    """Read a document directory's metadata, defaulting the missing fields.

    ``title`` defaults to the directory name, ``author`` to *user_name* when
    ``document_metadata.yaml`` is absent or does not carry the field. A metadata
    file whose YAML does not parse raises ``DocumentFormatError`` — the caller's
    file is wrong, and the reader needs to be told that rather than have a YAML
    error escape as a server fault.
    """
    attrs: dict[str, object] = {}
    metadata_path = document_dir / _METADATA_FILE
    if metadata_path.is_file():
        try:
            parsed = yaml.safe_load(metadata_path.read_text(encoding="utf-8"))
        except yaml.YAMLError as exc:
            raise DocumentFormatError(f"{_METADATA_FILE} is not valid YAML: {exc}") from exc
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
    write_back: bool = True,
) -> Document:
    """Return the graph Document for a document directory, creating it if missing.

    An existing Document is matched by title (case-insensitively) and reused
    as a shell (attrs and chapter ids — the import needs no paragraph
    hierarchy); a directory whose title no Document answers for is turned
    into a fresh
    NEW Document and persisted immediately, so later chapter imports can link
    to it. The resolved ``title``/``author`` are written back to the
    directory's ``document_metadata.yaml`` (preserving other keys) unless
    ``write_back`` is false.
    """
    matches = [row for row in document_repo.list_all() if str(row.get("title") or "").lower() == metadata.title.lower()]
    if matches:
        if len(matches) > 1:
            logger.warning("Multiple documents titled %r; reusing %r", metadata.title, matches[0]["id"])
        document = document_repo.load_shell(matches[0]["id"])
        if document is not None:
            return document
        logger.warning("Document %r listed but could not be loaded", matches[0]["id"])
    document = Document(title=metadata.title, author=metadata.author, state=DataState.NEW)
    uow = uow_factory.get_unit_of_work()
    uow.register(document)
    uow.commit()
    if write_back:
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


def _persist(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    uow_factory: UnitOfWorkFactory,
    document_id: str,
    chapter: Chapter,
    changed_paragraphs: list[Paragraph],
    added_paragraphs: list[Paragraph],
    nlp: Language,
) -> None:
    """Register the rebuilt chapter, its content-bearing paragraphs, and every
    sentence of those paragraphs (tokenized with *nlp*), then commit once."""
    tokenizer = SentenceTokenizer()
    doc_cache = DocCache(nlp)
    uow = uow_factory.get_unit_of_work()
    uow.register(chapter, document_id=document_id)
    for paragraph in changed_paragraphs + added_paragraphs:
        uow.register(paragraph, chapter_id=chapter.id)
        for sentence in paragraph.sentences:
            sentence.tokens[:] = tokenizer.tokenize(sentence.text, doc_cache)
            sentence.state = DataState.NEW
            uow.register(sentence, paragraph_id=paragraph.id)
    uow.commit()


def _build_chapter(chapter_id: str, diff: ChapterDiff, loaded: Chapter | None) -> Chapter:
    """Return the NEW chapter skeleton, or the already-loaded old chapter marked CHANGED."""
    if diff.created:
        return Chapter(
            id=chapter_id,
            title=diff.title,
            act=diff.act,
            category="Character" if diff.category == "Character" else "Chapter",
            state=DataState.NEW,
        )
    if loaded is None:
        raise ChapterMismatchError(f"Chapter '{chapter_id}' was not found in the knowledge graph")
    loaded.state = DataState.CHANGED
    return loaded


def _skeleton(front_id: str | None, title: str) -> Chapter:
    """Build the empty chapter side for detect_changes when no old chapter exists."""
    return Chapter(id=front_id or str(uuid.uuid4()), title=title)


def _build_paragraph(new: NewParagraph, nlp: Language) -> Paragraph:
    """Build a fresh NEW paragraph with Sentences sliced from *new*'s text."""
    paragraph = Paragraph()
    paragraph.sentences[:] = _split_sentences(new.text, nlp)
    paragraph.state = DataState.NEW
    return paragraph


def _apply_changed(chapter: Chapter, changed: ChangedParagraph, nlp: Language) -> Paragraph:
    """Replace *changed* paragraph's sentences and mark it CHANGED for persistence."""
    paragraph = next(p for p in chapter.paragraphs if p.id == changed.par_id)
    paragraph.sentences[:] = _split_sentences(changed.text, nlp)
    paragraph.state = DataState.CHANGED
    return paragraph


def _split_sentences(text: str, nlp: Language) -> list[Sentence]:
    """Split *text* into Sentence models on spaCy sentence boundaries.

    Newlines are never sentence delimiters: a mid-sentence newline stays inside
    the sentence's text, and a backslash-newline hard break is preserved. Each
    sentence keeps the whitespace up to the next sentence.
    """
    spans = list(nlp(text).sents)
    sentences = []
    for idx, span in enumerate(spans):
        end = spans[idx + 1].start_char if idx + 1 < len(spans) else len(text)
        sentence_text = text[span.start_char : end]
        if sentence_text.strip():
            sentences.append(Sentence(text=sentence_text))
    return sentences


def _place_new_paragraphs(chapter: Chapter, new_paragraphs: list[NewParagraph], nlp: Language) -> list[Paragraph]:
    """Insert every new paragraph and return them, in file order.

    Consecutive new paragraphs (same ``after_id``, or both ``at_start``) keep
    their file order by being placed after the previous placed paragraph;
    otherwise ``after_id``/``at_start``/append decide the position.
    """
    placed: list[Paragraph] = []
    previous_new: NewParagraph | None = None
    previous_placed: Paragraph | None = None
    for new in new_paragraphs:
        paragraph = _build_paragraph(new, nlp)
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
