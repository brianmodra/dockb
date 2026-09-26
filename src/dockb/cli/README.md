# Command-line interfaces

## Executive Summary

DockB is operated from the shell through two small commands under `python -m dockb.cli`: one that
imports a directory of markdown chapter files into the knowledge graph, and one that reconstructs a
single chapter from the graph back out as markdown. This document is the starting point for anyone
running or extending these tools; it says what each command does, what arguments it takes, and how
both connect to Neo4j.

Command-line entry points for DockB, run as Python modules. Both connect to Neo4j with the same
`NEO4J_URL`, `NEO4J_USER`, `NEO4J_PASSWORD` environment variables (or `.env`) the API server uses.

## Import a document directory

`python -m dockb.cli.import_document <document_dir> [--single-newline-paragraphs]` walks a
directory of markdown chapter files, diffing each against its chapter in the graph and persisting
changes. Each chapter file is matched through its front-matter `id`; changed or new files are
rewritten into the canonical span format (one identity span per paragraph). With
`--single-newline-paragraphs` each body line is read as a paragraph — for files whose paragraphs end
in a single newline and whose sentences run on inside a line — while the write-back stays canonical.
Chapter files living directly in the document directory, or anywhere beneath an `Act <name>`
subdirectory, are imported; a file's act is the name of its (`Act I`, `Act None`, …) directory, which
wins over any front-matter `act`. Other subdirectories are skipped. See
`../infrastructure/changes/README.md` for the diffing behavior.

## Reconstruct a chapter

`python -m dockb.cli.reconstruct_chapter <chapter_id> [--out PATH]` renders the chapter with
`chapter_id` from the knowledge graph as markdown. Without `--out` the canonical chapter file is
written into the server-owned tree — `<base>/<document title>/<Act X>/<chapter title>.md` under
`DOCKB_CHAPTERS_DIR` (defaulting to `cwd/dockb_chapters_dir`) — and git-committed; the written path
is printed. With `--out` it is written to the exact `PATH` instead, without touching the store tree.
A chapter id the graph does not know — or a chapter with no owning document (so it cannot be placed) —
prints the error message to stderr and exits non-zero. The serialization itself is the shared format
owned by `../infrastructure/markdown/`.