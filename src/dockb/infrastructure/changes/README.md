# Change Detection

`detect_changes` classifies what changed in a chapter between the **knowledge graph** and a
**newly saved markdown file**, at paragraph granularity. It is the diff step of the synchronous
save-and-rehydrate engine (see `README_markdown_redesign.md` §3 and §7-2): the loop reads the
hydrated chapter from Neo4j, parses only the new file, and rehydrates the paragraphs that changed.

## Contract

```python
detect_changes(old_chapter: Chapter, new_markdown: str, nlp: Language) -> ChapterDiff
```

- `old_chapter` — the hydrated `Chapter` pulled from the knowledge graph (paragraphs + sentences,
  read via `get_text()`). The old side is **never re-parsed**; only the new markdown file is parsed.
- `new_markdown` — the text of the saved file, including its YAML front matter.
- `nlp` — the spaCy pipeline (`spacy.load("en_core_web_sm")`) injected like the history package's
  `SnapshotReader`/`SnapshotWriter`. It splits span-free text and loose gaps into sentences; it is
  never used to re-derive sentence boundaries inside identity spans.

Returns a `ChapterDiff` (see below). Unchanged paragraphs are omitted entirely; the diff only
carries what the caller must rehydrate or delete.

### Front matter

The file must start with YAML front matter (`---\n…\n---`) whose `id` equals `old_chapter.id`. A
missing or mismatched `id` raises `ChapterMismatchError`; the file's identity must agree with the
knowledge graph it is being diffed against. The front matter is then stripped and only the body is
parsed. `title` and any extra attributes are ignored by this function.

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
  every sentence is replaced by the rehydrator.
- **unchanged** — id in both, sentence texts identical → **omitted entirely**.
- **new** — no id, or an id not present in the DB chapter → `NewParagraph(new_sentence_texts)`.
  A stale/unknown `data-par-id` is ignored: never reported, never stripped, never mutated.
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

@dataclass
class ChapterDiff:
    changed: list[ChangedParagraph] = field(default_factory=list)
    new: list[NewParagraph] = field(default_factory=list)
    deleted: list[str] = field(default_factory=list)
```

## Files

- `detect_changes.py` — the diff implementation plus the data structures above.
- `ChapterMismatchError` lives in `dockb/exceptions.py`, alongside the other domain exceptions.

See `README_markdown_redesign.md` §4 ("The sentence-boundary format rule") and §6 ("Sentence
metadata in the format") for the format; `../history/README.md` describes the writer/reader that
produce and consume the same span format.