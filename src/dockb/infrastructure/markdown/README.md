# Markdown Format

## Executive Summary

This note describes the markdown format of one chapter file: a short header, then a body the system can recognize again later. Import, history, and change detection all use this same format so they cannot drift apart.

It does not talk to the database. Whoever calls it loads the chapter first, then asks this package to read or write the text.

## Front matter

A chapter file may open with a YAML front-matter block delimited by `---` lines:

```
---
id: c-1
title: Chapter 1
---

<span data-par-id="p-1">
First sentence.
Second sentence.
</span>
```

`front_matter` exposes three helpers on a chapter file's full text:

- `parse(content)` -> `(attrs, body)`. With no opening `---` there is no front matter (`attrs` empty,
  `body` the whole content); otherwise `attrs` is the parsed mapping and `body` is everything after
  the closing `---` line. A block that is opened but never closed, or whose YAML is not a mapping,
  raises `ChapterMismatchError`; a block whose YAML does not parse raises `DocumentFormatError`. The
  second is its own type so a reader of an uploaded document can tell a malformed file from a
  fault of its own, and answer the caller for it rather than surfacing a YAML parser error.
- `render(attrs)` -> a complete delimited block.
- `merge(content, updates)` -> `content` with `updates` merged into its front matter, body
  untouched and existing attribute positions kept (new keys appended); a file with no front matter
  gets a block prepended.

History snapshots always carry front matter; `SnapshotReader` enforces that by rejecting content
that does not start with `---` (wrapping the parser's `ChapterMismatchError` as `SnapshotError`).
The import path treats missing front matter as a new chapter instead.

## Writing a chapter file

The writer turns a chapter model into a chapter file. `nlp` is accepted for
signature compatibility but is not used: the writer never sentence-splits. A
paragraph with sentences is written as a single identity span holding its
sentences, one per line; a paragraph (or a `dirty` chapter's blank-line block)
without sentences is wrapped raw into a fresh-id span. Paragraphs are separated
by blank lines:

```
<span data-par-id="p-1">
First sentence.
Second sentence.
</span>

<span data-par-id="p-2">
Next paragraph.
</span>
```

Rendering rules:

- Every paragraph is exactly one `<span data-par-id>` element. The newlines
  after the open tag and before the close tag are structural, not content; the
  parser strips them.
- A paragraph with sentences emits one rstripped sentence per line.
- A paragraph without sentences, and a `dirty` chapter's blank-line block, is
  wrapped as raw text in a **fresh-id** span (a paragraph id is never reused);
  the original paragraph id is written only for paragraphs that have sentences
  of their own.
- Sentence text is HTML-escaped; a backslash-newline hard break and soft
  newlines inside a sentence survive because the writer does not re-split text.
- The front matter is `attrs` verbatim when given, else the chapter's own identity
  (`render_chapter_markdown`). The front-matter block and body are joined by a blank
  line; an empty chapter renders as the block alone.

`SnapshotWriter` (history) feeds `{id, title, **chapter.model_extra}` as `attrs`; the import
write-back feeds the file's existing attributes plus the chapter's identity. The reader
and the change detector never write.
