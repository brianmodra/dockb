# Change Detection

## Executive Summary

This document specifies how a saved markdown chapter file is reconciled with the knowledge
graph. Two pieces implement it: `detect_changes` reports the paragraph-level changes between the
graph's chapter and the file — what to add, change, and delete, and where each new paragraph
belongs — and `apply_chapter_file` (a service in `services/markdown_import.py`) turns that report
into graph writes, after checking that the file's chapter really belongs to the document being
edited.

Only the new file is parsed; the chapter already in the graph is never re-parsed. The caller
rebuilds the chapter in memory from the diff and persists the whole chapter in one commit,
because paragraph order is only stored on the chapter-level edges. Read this document to learn
how chapter files map back into the graph, which files count as new vs edited, and what the
caller guarantees.

## Calling context

Chapter markdown files live in a directory hierarchy zero to a few levels deep below their
document's directory. The document directory is identified by name (e.g. `Linchpin/`); a
`document_metadata.yaml` beside it holds document extras (title, author, and later ISBN, synopsis,
etc.):

```
Linchpin/
    document_metadata.yaml
    Act I/
        Chapter 1.md
        Chapter 2.md
    Act II/
        Chapter 12.md
```

Chapters are identified by the front-matter `id` of their file. A chapter file always belongs to
the document it lives under: if the file's front matter names a chapter that is not a child of the
document being edited, that is an error, not a reason to create a chapter elsewhere.

`document_metadata.yaml` carries the document's `title` and `author` (strings). When the file is
absent, `title` defaults to the document directory's name and `author` to the current user name
(passed into the walker). The walker matches a directory to a graph `Document` by exact title and
reuses it (new chapters are appended to it, existing ones changed); a directory whose title no
document answers for becomes a new `Document` persisted before any chapter import, because the
chapter write path requires the parent `Document` node to already exist. (Later, an `id` field in
the yaml could replace the title-based match.)

The function this package contracts with is a **per-chapter-file** caller: it takes one markdown
chapter file and the hydrated `Document` it belongs to. `import_document_directory()` in
`dockb.services.markdown_import` is the directory-aware walker: it walks a document directory,
reads `document_metadata.yaml`, resolves the `Document`, and invokes the per-file caller once per
`*.md` file found recursively (in sorted order), returning one summary per file. A chapter file
whose front-matter `id` belongs to a different document aborts the whole directory import. A file
that is created during the import (its front matter carried no `id` the graph answered for) is
rewritten in place: the new chapter's `id` and `title` are merged into its front matter, any other
attributes being preserved; a file with a known `id` is left as it is.

## Contract

The caller reads the chapter file, derives the fallback title from the file name (the stem, i.e.
the file name without the `.md` extension, ignoring directory path), and calls:

```python
detect_changes(
    new_markdown: str,
    nlp: Language,
    get_chapter: Callable[[str], Chapter | None],
    create_chapter: Callable[[str | None, str], Chapter],
    title_fallback: str = "",
) -> ChapterDiff
```

- `new_markdown` — the text of the saved file, including any YAML front matter.
- `nlp` — the spaCy pipeline (`spacy.load("en_core_web_sm")`) injected like the history package's
  `SnapshotReader`/`SnapshotWriter`. It splits span-free text and loose gaps into sentences; it is
  never used to re-derive sentence boundaries inside identity spans.
- `get_chapter` — resolves the *old* hydrated chapter (read from the knowledge graph) by chapter id.
  It is called with the file's front-matter id when the file carries one. The old side is
  **never re-parsed**; only the new markdown file is parsed.
- `create_chapter` — builds the empty skeleton chapter when there is no old side. It receives the
  front-matter id (or `None` when the file has none) **and the chapter title**. When it receives
  `None` it assigns the new chapter's id itself.
- `title_fallback` — the caller's filename-derived title. It is used only when the front matter
  carries no `title`.

Returns a `ChapterDiff` (see below). The old chapter is whichever of `get_chapter` (found) or
`create_chapter` (fallback) produced the non-empty side; a file with no front matter therefore
means every block in the file is a new paragraph. Unchanged paragraphs are omitted entirely; the
diff only carries what the caller must rehydrate or delete.

### Front matter

Front matter is **optional**. When present, the file must start with it (`---\n…\n---`) and its
`id` selects the old chapter via `get_chapter`. A file that opens with `---` but is missing the
closing `---` raises `ChapterMismatchError`. `title`, when present, is the chapter title —
resolved over `title_fallback` and carried on `ChapterDiff.title`; any other attributes are
ignored by this function. When the file has no front matter (or no `id` inside it), there is no
old chapter to diff against: `get_chapter` is not called and `create_chapter` builds the skeleton.

## Parse rules (new markdown only)

- The body splits on a blank line (`\n\n`), giving one processing unit per **paragraph block**.
- A **span-bearing block** holds one `<span data-par-id="…">text</span>` per sentence, one per line.
  `data-par-id` is paragraph identity **only** — never part of the sentence text. Sentence text is
  the span's inner content, HTML-unescaped, tags stripped. The paragraph id is taken from the first
  `data-par-id` span in the block. Loose (unspanned) text inside a span-bearing block is
  sentence-split with `nlp` and kept at its position; nothing is dropped.
- A **span-free block** (hand-typed, pre-hydration) is sentence-split with `nlp` and yields no
  paragraph id.
- A newline inside a span is ordinary whitespace and is preserved byte-for-byte; a `\`-newline hard
  break is preserved. Each block is compared byte-for-byte (including trailing whitespace) so the
  rehydrator can keep its minimal-write guarantee.

## Classification

- **changed** — id present in the DB chapter and in the new file, sentence texts differ
  → `ChangedParagraph(id, new_sentence_texts)`. The paragraph's whole new sentence list is carried;
  every sentence is replaced by the caller.
- **unchanged** — id in both, sentence texts identical → **omitted entirely**.
- **new** — no id, or an id not present in the DB chapter → `NewParagraph(sentence_texts, …)`.
  A stale/unknown `data-par-id` is ignored: never reported, never stripped, never mutated.
  Positioning is described under "Data structures" below.
- **deleted** — DB paragraph ids absent from the new file → listed as ids only.

Merge case: old ids vanish (deleted) while the merged block carries either a surviving id
(changed) or none (new). There is no merge handling; the model is "delete + create new".

## Data structures

```python
@dataclass
class ChangedParagraph:
    par_id: str
    sentence_texts: list[str]

@dataclass
class NewParagraph:
    sentence_texts: list[str]
    after_id: str | None = None   # nearest preceding *surviving* paragraph, propagated across a run
    at_start: bool = False        # no surviving paragraph precedes it; chapter pre-exists non-empty

@dataclass
class ChapterDiff:
    changed: list[ChangedParagraph] = field(default_factory=list)
    new: list[NewParagraph] = field(default_factory=list)
    deleted: list[str] = field(default_factory=list)
    chapter_id: str = ""
    title: str = ""               # front-matter title, else title_fallback
    front_id: str | None = None   # the file's front-matter id, if any
    created: bool = False         # True when create_chapter supplied the old side
```

### New paragraph placement

Detection walks the file in block order, remembering which **existing** ids it has seen. Each new
paragraph is placed relative to the nearest preceding block that survives (an unchanged or changed
paragraph):

- `after_id` is that surviving paragraph's id. When two or more *consecutive* new paragraphs follow
  the same anchor, each carries the same `after_id`; the ordering between them is implied by the
  fact that the second was added after the first, and is recovered by the caller from
  `diff.new` order. A new paragraph never references a paragraph in `deleted` (deleted paragraphs
  are absent from the new file and so can never precede anything).
- `at_start` is set when the new paragraph is one of the *leading* blocks of the file — nothing
  survives before it — and the old chapter has at least one paragraph, so placing it first matters.
  A block in an empty old chapter (a brand-new chapter, or one emptied by this diff) carries no
  `at_start`; an empty chapter appends identically to inserting first. Leading runs keep
  `at_start` on every member; again the caller recovers internal order from `diff.new` order.

There is no insert-before-a-reference case, and no insert/append method field: `after_id` with a
reference means "insert immediately after"; `at_start` alone means "insert at the start", a
post-position always being expressible as "after its predecessor".

`chapter_id`, `title`, `front_id`, and `created` describe the chapter the diff was computed
against. `front_id` and `created` together let the caller enforce document membership (below).
`chapter_id` is the resolved chapter identity — the front-matter id of the diffed file when
present, otherwise the id assigned by `create_chapter` — so the caller learns a generated id.

## Applying the diff (the caller contract)

The caller receives the hydrated `Document`, the chapter file path, `nlp`, and the services needed
to load chapters and persist models. Its steps:

1. **Read and diff.** Read the file; derive `title_fallback` from the file stem; call
   `detect_changes` with `get_chapter`=chapter load, `create_chapter`=skeleton builder.
2. **Validate membership.** A chapter file always belongs to the document it lives under —
   - `created` and `front_id` is not `None`: the front matter names a chapter unknown to the
     knowledge graph, so it is not a child of this document → raise `ChapterMismatchError`.
   - `created` is false: the chapter was loaded by its front-matter id; it must be present in
     `document.chapters`, else it belongs to another document → raise `ChapterMismatchError`.
   - otherwise the chapter is genuinely new (no front-matter id): create it under `document`.
3. **Rebuild the chapter model**, starting from the returned old chapter, or from a fresh
   `Chapter(chapter_id, title)` for a new one:
   - *deleted* — remove the listed paragraph ids from `chapter.paragraphs`.
   - *changed* — for each `ChangedParagraph`, replace the paragraph's sentences with fresh
     `Sentence(text=…)` models (fresh ids) and mark it changed.
   - *new* — for each `NewParagraph` in `diff.new` order, build a fresh `Paragraph()` with
     `Sentence(text=…)` children, and position it:
     1. if it is consecutive to the previous new paragraph (same `after_id`, or both `at_start`),
        insert it immediately after that paragraph;
     2. else if `after_id` is set, insert it immediately after that existing paragraph
        (`chapter.insert_child(para, InsertionMode.AFTER, after=after_id)`);
     3. else if `at_start`, insert it first (`InsertionMode.FIRST`);
     4. else append it (`InsertionMode.LAST`).
4. **Persist.** Register the whole rebuilt chapter (its paragraph list fixes each paragraph's
   `index` on the `PART_OF` edge, and the chapter write path deletes paragraphs missing from it —
   which is the `deleted` set) *and* register each new/changed paragraph for its sentence content.
   Commit once.

The chapter is always registered with `document_id=<the hydrated document's id>` — matching the
`MATCH (d:Document {id: $document_id})` that opens the chapter write path, so the whole query runs
(the re-link on the `PART_OF` edge is an idempotent `MERGE`). An empty diff (nothing to add,
change, or delete) persists nothing: an unchanged file re-save is a no-op, and a brand-new empty
chapter is reported as `created` but is not written until it gains content.

Paragraph ordering is persisted as `index` on the `(Paragraph)-[:PART_OF]->(Chapter)` edge. The
paragraph-level write path (`ParagraphRepository`) does **not** set this index; ordering is
guaranteed only when the caller persists the whole rebuilt chapter, which is why step 4 is
chapter-level. New/changed paragraph *content* is written paragraph-level. `HistoryService.restore`
is the precedent for whole-chapter persistence.

## Files

- `detect_changes.py` — the diff implementation plus the data structures above.
- `ChapterMismatchError` lives in `dockb/exceptions.py`, alongside the other domain exceptions.
- The per-chapter-file caller is `services/markdown_import.py` (`apply_chapter_file`), a service
  consumer of this package; `composition.py` is where it will be wired.

See `README_markdown_redesign.md` §4 ("The sentence-boundary format rule") and §6 ("Sentence
metadata in the format") for the format; `../history/README.md` describes the writer/reader that
produce and consume the same span format.