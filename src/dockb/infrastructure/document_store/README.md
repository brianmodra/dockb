# Document Store

## Executive Summary

The document store owns the server-side markdown file tree that backs the document
lifecycle described in `README_markdown_redesign.md`. The backend, not the editor,
writes these files: one directory per document id, holding a `document_metadata.yaml`
(title/author) and one `chapter-{id}.md` per chapter. The store resolves those paths
from ids only and rejects any id that could escape the base directory, so untrusted
client-supplied ids cannot read or write outside the tree.

Read this to learn what the on-disk layout is, and where a document's files live.

## Layout

Everything lives under one base directory, configured with the `DOCKB_CHAPTERS_DIR`
environment variable (`DocumentStore.from_env()` requires it set; at server startup
`resolve_document_base_dir` in `composition.py` defaults it to `cwd`/`dockb_chapters_dir`
when unset, creating the directory and git-initializing it so the store can own the repo).
The tree:

```
<base>/
    <document_id>/
        document_metadata.yaml
        chapter-<chapter_id>.md
```

- `document_id` and `chapter_id` are used verbatim as path segments. The store is
  used with uuid ids (the graph's model ids), but any id is accepted as long as it
  is a single safe segment.
- Path resolution never inspects the graph; the store only maps ids to paths and
  reads/writes files. Hydration of a chapter file into the graph is the caller's
  job (`services/markdown_import.py::apply_chapter_file`).

## Path safety

`DocumentStore._validate` runs on every id before any path is built. It rejects
empty ids and ids containing `.` or `..` as a segment, a path separator (`/` or
`\`), an absolute path, or control characters. Because paths are then built by
joining these validated single-segment ids under the base directory, no
id-derived path can escape the tree. All write methods create parent directories
on demand.

## Metadata

`document_metadata.yaml` is a YAML mapping carrying at least `title` and `author`.
`write_metadata` preserves any other keys already present in the file, so callers
may add their own fields without losing them on the next write; `read_metadata`
returns the two fields (missing ones default to empty strings), or `None` when the
file does not exist. `DocumentMetadata` is the single definition of this pair,
shared with the directory import in `services/markdown_import.py`.

## Git

The base directory is a git repository (the server owns it, as described in
`README_markdown_redesign.md`). `git_commit(document_id, message)` stages only
the document's directory — `git add -- <document_id>` — and commits it;
whether anything is staged is decided by `git status --porcelain -- <document_id>`
alone, so unrelated untracked files left in the tree (e.g. runtime state) are
never committed and never trip the commit. A document with nothing new to
commit is a no-op — the call does not fail on git's "nothing to commit". This
is how newly materialized trees enter history with a single commit.