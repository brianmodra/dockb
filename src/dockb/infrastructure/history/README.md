# History Snapshots

## Executive Summary

Before every edit to a chapter, DockB rewrites a snapshot file of that chapter's full content so
that edits can be undone or restored. This document describes that snapshot file: how it is named
and stored in git, what its markdown structure carries, and how the snapshot writer and reader
produce and consume it. The snapshot's markdown format is the same canonical per-paragraph span
format owned by `infrastructure/markdown/`; the writer here delegates serialization to that shared
package.

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

<span data-par-id="p-uuid-1">
Paragraph one first sentence.
Paragraph one second sentence.
</span>

<span data-par-id="p-uuid-2">
Paragraph two first sentence.
</span>
```

- **Front matter** (YAML between `---` delimiters) holds chapter attributes
  (title, id, order, etc.)
- **Paragraph** = a block delimited by a blank line (`\n\n`), written as one
  inline `<span data-par-id="…">` element wrapping the whole paragraph; the
  paragraph's sentences sit inside it, one per line. The paragraph's UUID is
  written once, on the span, so paragraph identity survives any edit to the
  paragraph's text. The span markup is invisible to markdown renderers and
  carries the paragraph id the rehydration loop needs.
- **Sentences carry no id in the format.** They are re-derived at read time and
  assigned freshly generated UUIDs.
- **The span is the paragraph unit.** The writer emits one span per model
  paragraph and does not re-run sentence splitting; the newline after the open
  tag and before the close tag are structural, not content. Text that arrived
  without spans (hand-typed, legacy files, dirty chapters) is wrapped raw in a
  freshly generated-id span.
- **Spans only mark identity.** The same span mechanism later carries any other
  attribute the NLP layer derives (`data-triple` / `data-spo`, etc.), per the
  markdown redesign. Only `data-par-id` is interpreted by the serializer and
  parser today.
- **Newlines join sentences, never sentence delimiters.** The canonical layout
  is one sentence per line inside the span; the parser keeps the inter-sentence
  newline as trailing whitespace of the previous sentence, so the paragraph
  reads back byte-for-byte. A newline *inside* a sentence is ordinary whitespace
  (soft wrapping) and is preserved; a forced mid-sentence break is `\` followed
  by a newline (CommonMark hard break), also preserved inside the span. Span-free
  text is delimited only by spaCy sentence boundaries.
- **Escaping.** Sentence text is HTML-escaped on write and unescaped on read,
  so a literal `<span>` or `&` in the text cannot be confused with markup. The
  parser ignores span boundaries that cross a blank line.

Writing normalizes to the one-span-per-paragraph form; reading restores paragraph
UUIDs from the spans, re-derives sentences with spaCy from the paragraph text,
and falls back to a spaCy split (fresh UUIDs) for span-free blocks. Both directions
are idempotent, so paragraphs the caller
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
| `snapshot_writer.py` | Serialize a chapter to markdown via `infrastructure/markdown`'s shared writer (one `<span data-par-id>` per paragraph, sentence lines inside; raw-text wrap for span-free content) and write to disk |
| `snapshot_reader.py` | Parse a markdown snapshot back into model objects (paragraph UUIDs restored from spans; spaCy-injected split for span-free text) |

The `HistoryService` (in `services/`) orchestrates these components and
coordinates with edits.

## API

See [`src/dockb/controllers/README_API.md`](../controllers/README_API.md) for
the REST endpoints that expose snapshot listing and undo/redo operations.
