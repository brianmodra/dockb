# Document Store

## Executive Summary

This note describes the folder where DockB keeps each account's markdown. The server writes those files; the editor never does. Every account has its own directory and its own git repository below one shared base directory, so a document's files live under the account that owns it and a commit can never span two accounts. A store is scoped to one account by construction and names that account by its internal id rather than a username, so nothing a user can rename can move a tree.

Read it to see where a chapter file lands, including supporting character chapters, why a document title becomes a path segment and what makes one unsafe, and how a rename, delete or adoption stays in git. It also names the two operations on the older, owner-less layout that only the backfill command uses, and why a manuscript that belonged to no account had no tree at all.

## Layout

Everything lives under one base directory, configured with the `DOCKB_CHAPTERS_DIR`
environment variable (`DocumentStoreFactory.from_env()` requires it set; at server startup
`resolve_document_base_dir` in `composition.py` defaults it to `cwd`/`dockb_chapters_dir`
when unset, creating the directory but not a repository in it). Under it, one directory
per account, each an independent git repository that the store creates on first use. The
tree:

```
<base>/
    <account_id>/
        .git/
        <document_title>/
            document_metadata.yaml
            Act <name>/
                <chapter_title>.md
            Act None/
                <chapter_title>.md
            Characters/
                <chapter_title>.md
```

Before trees were per-account, a document's directory sat at `<base>/<document_title>`
with no account segment at all. `DocumentStore` is scoped to an account by construction
and cannot name that path, so the two operations on the older layout live on the factory:
`legacy_document_dir(document_title)` returns it (validating the title as a single path
segment, since a hostile title must not be able to name a directory outside the base) and
`remove_legacy_document(document_title)` deletes it. The removal is not committed: the
repository that once lived at the base directory is the one the per-account repositories
replaced, nothing reads it any more, and an account's own repository is never asked to
record a path outside it. `dockb users assign` reads and writes both layouts, which is how
a manuscript imported before accounts owned documents arrives in an account's tree.

- `<account_id>` is the internal account id (`users.id`), not a username. Usernames are
  mutable provider data — a rename or a merge would otherwise move or split a tree — and
  an id is minted once and never changes.
- A `DocumentStore` is scoped to exactly one account: `DocumentStore(base_dir, account_id)`
  refuses a blank id, and `DocumentStoreFactory.for_account(account_id)` hands out the
  store for one account. Services hold the factory rather than a store, so the account a
  write lands under is decided by the request being served rather than by whichever call
  site remembered to pass a store.
- A document with no `owner` in the graph — one imported before accounts owned documents —
  has no tree and no account to serve it. `dockb users assign` gives it one; nothing that
  serves a request can reach it.
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

A document title, a chapter title, a chapter's act, and the account id all become
path segments under the base directory, so each must be a single segment that
cannot climb out of the tree. That rule is not the store's — it belongs to the value, not to the
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
directory name (so an act like `Act ../../x` cannot escape either). The constructor
applies the same rule to the account id. Because paths are then built by joining
these validated single segments under the base directory, no derived path can
escape the tree. All write methods create parent directories on demand.

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

Each account's directory is its own git repository, created on first use, so a
commit contains one account's documents and nothing else. (The snapshot writer
keeps a separate base directory and repository of its own; the document base
directory is deliberately not a repository.) `git_commit(document_title, message)`
runs inside that repository, stages only the document's directory —
`git add -- <account_id>/<document_title>` — and commits it; whether anything is
staged is decided by `git status --porcelain -- <document_title>` alone, so
unrelated untracked files left in the account's tree (e.g. runtime state) are
never committed and never trip the commit. A document with nothing new to commit
is a no-op — the call does not fail on git's "nothing to commit" — as is a
document whose directory does not exist on disk, which is what "not on disk"
already means to `remove_document` and `rename_document`. This is how newly
materialized trees enter history with a single commit.

`remove_document(document_title)` and `remove_chapter(...)` undo ownership:
each removes its files from disk and from git (`git rm`, committed), in both
cases tolerating files that were never tracked and directories that are
already gone. Deleting a document therefore removes its manuscript as well as
its graph subtree. `remove_chapter` also deletes the act, `Characters`, and document directories
when the removal empties them, so `document_exists` stays accurate once the
last chapter of a document is removed. The services call these before marking
the graph node `DELETED`, so a store failure leaves the graph intact for a
retry and the DELETE endpoint leaves no markdown files behind.

`adopt_document(document_title, source)` copies a document's directory from
`source` into this account's tree and commits it there. Copying rather than
moving means a failure part way through leaves the original where it was, and
committing here means the manuscript enters this account's history as its first
commit — history does not travel between repositories, and stitching it across
would buy a tree that only ever held one account's work. It refuses to write
over an existing directory instead of merging into it, because two documents'
files under one directory is a manuscript neither account wrote. A `source`
that is not a directory is a no-op: the document's content is in the graph
regardless, and the editor materializes a tree on first open.

`rename_document(old, new)` and `rename_chapter(..., old, new)` are the mirror
image: a title rename moves the owned directory or markdown file, so a rename
never leaves a stale title-keyed tree behind.