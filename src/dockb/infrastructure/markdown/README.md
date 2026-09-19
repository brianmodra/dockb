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

## Writing a chapter file

`writer.render_chapter_markdown(chapter, nlp, attrs=None)` serializes one chapter to a complete
chapter file — front matter block plus body — and `writer.write_chapter_markdown(chapter, path,
nlp, attrs=None)` renders and writes it. `writer.serialize_body(chapter, nlp)` returns just the
body. `nlp` is required: span-free text (a dirty chapter, or a paragraph without sentences) is
split into sentences with spaCy before being wrapped.

The body is one identity span per sentence, paragraphs separated by blank lines:

```
<span data-par-id="p-1">First sentence.</span>
<span data-par-id="p-1">Second sentence.</span>

<span data-par-id="p-2">Next paragraph.</span>
```

Rendering rules:

- A paragraph without sentences is wrapped so each sentence is a fresh-id span (never reuses a
  paragraph id); the original paragraph id is used only when the paragraph has sentences of its
  own.
- Sentence text is HTML-escaped; a backslash-newline hard break and soft newlines inside a
  sentence survive because spaCy never breaks on newlines.
- The front matter is `attrs` verbatim when given, else `{id, title}` from the chapter. The
  front-matter block and body are joined by a blank line; an empty chapter renders as the block
  alone.

`SnapshotWriter` (history) feeds `{id, title, **chapter.model_extra}` as `attrs`; the import
write-back feeds the file's existing attributes with `id`/`title` set to the chapter's. The reader
and the change detector never write.
