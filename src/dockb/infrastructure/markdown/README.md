# Markdown Format

## Executive Summary

This package owns the on-disk markdown format for a single chapter: its YAML front matter and the
canonical body in which every sentence is an identity span. It is the one implementation of that
format, shared by the directory import (`services/markdown_import.py`), the history snapshots
(`infrastructure/history/`), and the change detector (`infrastructure/changes/detect_changes.py`),
so those callers cannot drift apart. Read this to learn how a chapter file's front matter is
parsed, rendered, and merged without touching the body.

The package holds no repository or Neo4j code: it operates on strings and models only. Loading a
chapter from the graph before serialising it belongs to its caller (see
`services/markdown_export.py`).

## Front matter

A chapter file may open with a YAML front-matter block delimited by `---` lines:

```
---
id: c-1
title: Chapter 1
---

<span data-par-id="p-1">Body sentence.</span>
```

`front_matter.parse(content)` returns `(attrs, body)`:

- With no opening `---`, there is no front matter: `attrs` is empty and `body` is the whole
  content unchanged.
- With a block, `attrs` is the parsed mapping and `body` is everything after the closing `---`
  line (including the newline that follows it).
- A block that is opened but never closed, or whose YAML is not a mapping, raises
  `ChapterMismatchError`.

`front_matter.render(attrs)` produces a complete delimited block; `front_matter.merge(content,
updates)` returns `content` with `updates` merged into its front matter, preserving the body and
the position of any attributes the caller did not set (new keys are appended). A file with no
front matter gets a rendered block prepended.

History snapshots always carry front matter; `SnapshotReader` enforces that by rejecting content
that does not start with `---` (wrapping the parser's `ChapterMismatchError` as `SnapshotError`).
The import path treats missing front matter as a new chapter instead.
