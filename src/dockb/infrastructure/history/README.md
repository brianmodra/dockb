# History Snapshots

Every edit to a chapter rewrites a **snapshot file** of the chapter's full content
*before* the edit is applied. This enables:

- **Undo/redo** — replay snapshots in reverse chronological order
- **Disaster recovery** — restore from a snapshot after a bug or system failure

## File Format

Snapshots are saved as **markdown** with structured metadata embedded
in the document.

### Naming

There will only be one file per chapter, named by the chapter UUID as so:

```
chapter-{UUID}.md
```

### Using GIT commits

When a new file is written, it is also committed and pushed to a local GIT repo. Its GIT commit ID
will be what identifies the edit.

### Structure

```
---
title: "Chapter 1"
id: "c-uuid-1"
order: 1
(... other chapter attrs ...)
---

<span data-par-id="p-uuid-1">Paragraph one first sentence.</span>
<span data-par-id="p-uuid-1">Paragraph one second sentence.</span>

<span data-par-id="p-uuid-2">Paragraph two first sentence.</span>
```

- **Front matter** (YAML between `---` delimiters) holds chapter attributes
  (title, id, order, etc.)
- **Paragraph** = a block delimited by a blank line (`\n\n`).
- **Sentence** = one inline `<span data-par-id="…">` element per line inside a
  paragraph. The paragraph's UUID is repeated on every sentence span it
  contains, so paragraph identity survives any single-sentence edit. The span
  markup is invisible to markdown renderers and carries the paragraph id the
  rehydration loop needs.
- **Sentences carry no id in the format.** They are re-derived at read time and
  assigned freshly generated UUIDs.
- **The span is the sentence unit.** The writer emits one span per model
  sentence, one per line. It reads the sentence text from the model and does
  not re-run sentence splitting over it. Text that was written without spans
  (hand-typed, or legacy files) is split with spaCy on write and is given
  freshly generated paragraph and sentence UUIDs.
- **Spans only mark identity.** The same span mechanism later carries any other
  attribute the NLP layer derives (`data-triple` / `data-spo`, etc.), per the
  markdown redesign. Only `data-par-id` is interpreted by the serializer and
  parser today.
- **Newlines are never sentence delimiters.** Sentences are delimited by their
  spans. A newline inside a span is ordinary whitespace (soft wrapping) and is
  preserved byte-for-byte; a forced mid-sentence break is `\` followed by a
  newline (CommonMark hard break), also preserved inside the span. Span-free
  text is delimited only by spaCy sentence boundaries.
- **Escaping.** Sentence text is HTML-escaped on write and unescaped on read,
  so a literal `<span>` or `&` in the text cannot be confused with markup. The
  parser ignores span boundaries that cross a blank line.

Writing normalizes to the one-span-per-line form; reading restores paragraph
UUIDs from the spans and falls back to a spaCy split (fresh UUIDs) for
span-free blocks. Both directions are idempotent, so paragraphs the caller
did not change serialize unchanged — the minimal-diff property the rehydration
loop relies on. Both classes take the same injected spaCy pipeline
(`spacy.load("en_core_web_sm")` and siblings) used by the semantics services.

See [`../../../../README_markdown_redesign.md`](../../../../README_markdown_redesign.md)
for the design rationale (section 4, "The sentence-boundary format rule").

## Retention

The number of retained snapshots per chapter is "infinite" because the whole chapter will be stored
in GIT from start to finish.

## Snapshot Management

The `infrastructure/history/` package contains:

| Component | Responsibility |
|---|---|
| `snapshot_writer.py` | Serialize a chapter to markdown via `infrastructure/markdown`'s shared writer (per-sentence `<span data-par-id>` lines, spaCy split for span-free text) and write to disk |
| `snapshot_reader.py` | Parse a markdown snapshot back into model objects (paragraph UUIDs restored from spans; spaCy-injected split for span-free text) |

The `HistoryService` (in `services/`) orchestrates these components and
coordinates with edits.

## API

See [`src/dockb/controllers/README_API.md`](../controllers/README_API.md) for
the REST endpoints that expose snapshot listing and undo/redo operations.
