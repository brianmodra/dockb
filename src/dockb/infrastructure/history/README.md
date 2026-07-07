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

Chapter text goes here.

<!-- {"premise": "...", "elevator_pitch": "..."} -->

A <span data-attr="something">word</span> in context.
```

- **Front matter** (YAML between `---` delimiters) holds chapter attributes
  (title, id, order, etc.)
- **JSON blobs** in HTML comments hold non-text attributes (e.g. premise,
  elevator pitch) that don't map naturally to markdown
- **HTML `<span>` elements** with `data-attr` attributes hold inline
  formatting or structural metadata where appropriate

## Retention

The number of retained snapshots per chapter is "infinite" because the whole chapter will be stored
in GIT from start to finish.

## Snapshot Management

The `infrastructure/history/` package contains:

| Component | Responsibility |
|---|---|
| `snapshot_writer.py` | Serialize a chapter to markdown and write to disk |
| `snapshot_reader.py` | Parse a markdown snapshot back into model objects |

The `HistoryService` (in `services/`) orchestrates these components and
coordinates with edits.

## API

See [`src/dockb/controllers/README_API.md`](../controllers/README_API.md) for
the REST endpoints that expose snapshot listing and undo/redo operations.
