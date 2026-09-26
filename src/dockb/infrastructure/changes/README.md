# Change Detection

## Executive Summary

This document specifies how markdown chapter files are brought back into the knowledge graph. One
piece, `detect_changes`, turns a saved file into a paragraph-level report — what to add, change, and
delete, and where each new paragraph goes — without ever re-parsing the chapter the graph already
holds. A second piece, `apply_chapter_file`, puts that report into effect as graph writes after
checking the file's chapter really belongs to the document being edited.

`import_document_directory` then drives the whole process from the shell: it walks a document's
directory for chapter files — markdown files inside `Act <name>` directories whose numbered names
(and numbered acts) fix the import order — resolves the directory to one `Document` from its
metadata (`document_metadata.yaml`), writes that metadata back when it creates the `Document`,
imports each chapter file, and rewrites any file whose graph content changed into the canonical
span format — front matter plus one identity span per paragraph — so the next import matches it.
Read this document to learn how chapter files map back into the graph, which files count as new
versus edited, what the caller guarantees, and how a document directory becomes graph data.

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
chapter write path requires the parent `Document` node to already exist. Creating that `Document`
also writes the resolved `title`/`author` into `document_metadata.yaml`, preserving any other
attributes already in the file, so the derived values are explicit on the next run. (Later, an `id`
field in the yaml could replace the title-based match.)

The function this package contracts with is a **per-chapter-file** caller: it takes one markdown
chapter file and the hydrated `Document` it belongs to. `import_document_directory()` in
`dockb.services.markdown_import` is the directory-aware walker: it walks a document directory,
reads `document_metadata.yaml`, resolves the `Document`, and invokes the per-file caller once per
chapter file — `*.md` files inside a top-level `Act <name>` directory, processed in act-number
order (digits, Roman numerals, or the Unicode single-character numerals, with `Act None` first)
then by the file's sequence number with at most one letter — trailing at the end or embedded
between spaces in the name (5, 5a, 5b, 6; "Bad Guys Close In 48 Jael" → 48) — returning one
summary per file. Root-level and non-act files are not chapters. A malformed act name, an
unnumbered chapter file, or two acts or two files numbering the same abort the walk. A chapter file
whose front-matter `id` belongs to a different document aborts the whole directory import. When the
file's diff is non-empty the caller rewrites the file in place from the rebuilt chapter: the front
matter carries the chapter `id` and `title`, any other attributes being preserved in place, and the
body is written in the canonical span format — one `<span data-par-id=…>` per paragraph holding its
sentences one per line, paragraphs separated by blank lines — so the file stays the graph's source of
truth. A file whose
diff is empty and that is not a brand-new chapter is left untouched; a brand-new empty chapter is
still given an identity: it is persisted as an empty chapter and its file receives the front-matter
`id`/`title` only (with no body). From a shell,
`python -m dockb.cli.import_document <document_dir>` drives the walker.

## Contract

The caller reads the chapter file, derives the fallback title from the file name (the stem, i.e.
the file name without the `.md` extension, ignoring directory path), and calls:

```python
detect_changes(
    new_markdown: str,
    get_chapter: Callable[[str], Chapter | None],
    create_chapter: Callable[[str | None, str], Chapter],
    title_fallback: str = "",
    single_newline_paragraphs: bool = False,
) -> ChapterDiff
```

- `new_markdown` — the text of the saved file, including any YAML front matter.
- `get_chapter` — resolves the *old* hydrated chapter (read from the knowledge graph) by chapter id.
  It is called with the file's front-matter id when the file carries one. The old side is
  **never re-parsed**; only the new markdown file is parsed.
- `create_chapter` — builds the empty skeleton chapter when there is no old side. It receives the
  front-matter id (or `None` when the file has none) **and the chapter title**. When it receives
  `None` it assigns the new chapter's id itself.
- `title_fallback` — the caller's filename-derived title. It is used only when the front matter
  carries no `title`.
- `single_newline_paragraphs` — treat every body line as a paragraph block instead of the usual
  blank-line separation, for files whose paragraphs end in a single newline and whose sentences run
  on inside a line (see "Parse rules").

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

- The body splits on a blank line (`\n\n`), giving one processing unit per **paragraph block**
  (with `single_newline_paragraphs`, every body line is a block instead — see below).
- A **span-bearing block** holds one `<span data-par-id="…">` wrapping the whole paragraph; the
  span's inner text minus the structural newlines after the open tag and before the close tag is
  the paragraph text. `data-par-id` is paragraph identity **only** — never part of the paragraph
  text. Loose (unspanned) text before, between, and after spans is kept at its position; nothing
  is dropped. The paragraph id is taken from the first `data-par-id` span in the block.
- A **span-free block** (hand-typed, pre-hydration) yields no paragraph id.
- A block yields **raw paragraph text**, not sentences: the caller splits it with spaCy. Sentence
  splitting is never this package's job.
- A newline inside a span is ordinary whitespace and is preserved byte-for-byte; a `\`-newline hard
  break is preserved. Each block is compared byte-for-byte (including trailing whitespace) so the
  rehydrator can keep its minimal-write guarantee.

### Single-newline paragraphs

With `single_newline_paragraphs` a body line is a paragraph block instead of a blank line, so files
whose paragraphs end in a single newline and whose sentences run on inside a line import correctly.
The lines that belong to a span-wrapped paragraph (the structural open-tag, sentence, and close-tag
lines) stay together as one block, so a canonical file re-imported under the mode is not shredded
into fake paragraphs. The write-back is always canonical.

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

`ChangedParagraph`, `NewParagraph`, and `ChapterDiff` are defined in `detect_changes.py`. Beyond
the three change lists, `ChapterDiff` carries `chapter_id` — the resolved chapter identity, the
file's front-matter id or the id `create_chapter` assigned — `title`, `front_id`, and `created`,
which together let `apply_chapter_file` enforce document membership and learn a generated id.

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
(the re-link on the `PART_OF` edge is an idempotent `MERGE`). A non-empty diff also rewrites the
source file from the rebuilt chapter (front matter plus span-form body), so file and graph agree
after every change. An empty diff persists nothing *except* when the chapter is brand-new: a
brand-new empty chapter is still registered (an empty chapter, fixing its identity in the graph) and
its file gets the front-matter `id`/`title`, so a later re-import resolves it instead of treating it
as a foreign id. An unchanged file re-save remains a no-op.

Paragraph ordering is persisted as `index` on the `(Paragraph)-[:PART_OF]->(Chapter)` edge. The
paragraph-level write path (`ParagraphRepository`) does **not** set this index; ordering is
guaranteed only when the caller persists the whole rebuilt chapter, which is why step 4 is
chapter-level. New/changed paragraph *content* is written paragraph-level. `HistoryService.restore`
is the precedent for whole-chapter persistence.

## Files

- `detect_changes.py` — the diff implementation plus the data structures above.
- `ChapterMismatchError` lives in `dockb/exceptions.py`, alongside the other domain exceptions.
- The per-chapter-file caller is `services/markdown_import.py` (`apply_chapter_file`), a service
  consumer of this package; wiring it into the app is tracked in `../../../../README_todo.md`.

See `README_markdown_redesign.md` §4 ("The sentence-boundary format rule") and §6 ("Sentence
metadata in the format") for the format; `../history/README.md` describes the writer/reader that
produce and consume the same span format. Both that writer and the write-back above delegate to
the shared serializer in `../markdown/`.