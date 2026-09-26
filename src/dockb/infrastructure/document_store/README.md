# Document Store

## Executive Summary

DockB's markdown-is-source-of-truth design lives on disk in the document store: a tree of
chapter files that the backend — never the editor — writes, keyed by titles the graph owns, so
paths are always under the store's control. Read this to learn the on-disk layout, how title
paths are kept escape-proof, and how the store's git commits work. Hydration of a file back into
the knowledge graph is the caller's job, not the store's.

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
```

- `document_title`, `act`, and `chapter_title` come from the graph and are used
  verbatim as path segments. An empty act maps to the reserved `Act None`
  directory; an act already prefixed `Act ` is used as-is, otherwise the prefix is
  applied (`II` → `Act II`).
- Path resolution never inspects the graph; the store only maps titles to paths
  and reads/writes files. Hydration of a chapter file into the graph is the
  caller's job (`services/markdown_import.py::apply_chapter_file`).
- `list_chapter_files(document_title)` returns the chapter markdown files under a
  document, sorted by path.

## Path safety

`DocumentStore._validate_title` runs on every title before any path is built —
the document title, the chapter title, and the *derived* act directory name
(so an act like `Act ../../x` cannot escape either). It rejects empty titles and
titles containing `.` or `..` as a segment, a path separator (`/` or `\`), or
control characters. Because paths are then built by joining these validated
single-segment titles under the base directory, no title-derived path can escape
the tree. All write methods create parent directories on demand.

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