# Document Store

## Executive Summary

This note describes the folder where DockB keeps each document's markdown. The server writes those files. The editor never does. Paths come from titles the graph already owns, so a hostile title cannot escape the folder.

Read it to see where a chapter file lands, including supporting character chapters, and how a rename or delete stays in git. A failed file change leaves the graph recoverable.

## Layout

Everything lives under one base directory, configured with the `DOCKB_CHAPTERS_DIR`
environment variable (`DocumentStore.from_env()` requires it set; at server startup
`resolve_document_base_dir` in `composition.py` defaults it to `cwd`/`dockb_chapters_dir`
when unset, creating the directory and git-initializing it so the store can own the repo).
The tree:

```
<base>/
    <document_title>/
        document_metadata.yaml
        Act <name>/
            <chapter_title>.md
        Act None/
            <chapter_title>.md
        Characters/
            <chapter_title>.md
```

- `document_title`, `act`, and `chapter_title` come from the graph and are used
  verbatim as path segments. An empty act maps to the reserved `Act None`
  directory; an act already prefixed `Act ` is used as-is, otherwise the prefix is
  applied (`II` → `Act II`). A `Character` chapter always lives under the reserved
  `Characters` directory, whatever its act — never under `Act None`.
- Path resolution never inspects the graph; the store only maps titles to paths
  and reads/writes files. Hydration of a chapter file into the graph is the
  caller's job (`services/markdown_import.py::apply_chapter_file`).
- `list_chapter_files(document_title)` returns the chapter markdown files under a
  document, sorted by path.

## Path safety

A document title, a chapter title, and a chapter's act all become path segments
under the base directory, so each must be a single segment that cannot climb out
of the tree. That rule is not the store's — it belongs to the value, not to the
layer that uses it, and the wire schema has to reject the same inputs or an
editor would have to satisfy two contracts. It therefore lives in
`dockb/titles.py`: `is_unsafe_segment(value)` reports whether *value* cannot be a
path segment, and `validate_segment(value)` raises `ValueError` naming it. A
value is unsafe when it is empty, is `.` or `..`, contains a path separator
(`/` or `\`), or contains a control character (`ord < 32`, or `127`). Names that
merely *look* like traversal are fine: `...`, `..a`, `a..`, and `.hidden` are all
legal single segments.

`DocumentStore._validate_title` calls `validate_segment` on every title before
any path is built — the document title, the chapter title, and the *derived* act
directory name (so an act like `Act ../../x` cannot escape either). Because paths
are then built by joining these validated single segments under the base
directory, no title-derived path can escape the tree. All write methods create
parent directories on demand.

The schemas add the rule to the API, which turns a hostile title into a `422`
(`controllers/schemas/documents.py::DocumentAttrs.title_not_blank` and
`controllers/schemas/nodes.py::ChapterAttrs.title_not_blank`). A schema rejects
the same unsafe segments plus blank and whitespace-only titles, which the store
permits — a whitespace directory is filesystem-legal, so the store has no reason
to refuse it, while a whitespace *title* is meaningless. The one-sided rule is
that the schema is never looser than the store: any title the store can place on
disk is accepted by the API. `ChapterAttrs.act` is checked for the same reason,
but not for blankness, because an empty act is legitimate and maps to the
reserved `Act None` directory.

## Metadata

`document_metadata.yaml` is a YAML mapping carrying at least `title` and `author`.
`write_metadata` preserves any other keys already present in the file, so callers
may add their own fields without losing them on the next write; `read_metadata`
returns the two fields (missing ones default to empty strings), or `None` when the
file does not exist. `DocumentMetadata` is the single definition of this pair,
shared with the directory import in `services/markdown_import.py`.

## Git

The base directory is a git repository (the server owns it, as described in
`README_markdown_redesign.md`). `git_commit(document_title, message)` stages only
the document's directory — `git add -- <document_title>` — and commits it;
whether anything is staged is decided by `git status --porcelain -- <document_title>`
alone, so unrelated untracked files left in the tree (e.g. runtime state) are
never committed and never trip the commit. A document with nothing new to
commit is a no-op — the call does not fail on git's "nothing to commit". This
is how newly materialized trees enter history with a single commit.

`remove_document(document_title)` and `remove_chapter(...)` undo ownership:
each removes its files from disk and from git (`git rm`, committed), in both
cases tolerating files that were never tracked and directories that are
already gone. `remove_chapter` also deletes the act, `Characters`, and document directories
when the removal empties them, so `document_exists` stays accurate once the
last chapter of a document is removed. The services call these before marking
the graph node `DELETED`, so a store failure leaves the graph intact for a
retry and the DELETE endpoint leaves no markdown files behind.

`rename_document(old, new)` and `rename_chapter(..., old, new)` are the mirror
image: a title rename moves the owned directory or markdown file, so a rename
never leaves a stale title-keyed tree behind.