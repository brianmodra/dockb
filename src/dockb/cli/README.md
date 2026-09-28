# Command-line interfaces

## Executive Summary

These are DockB's two shell commands for chapter files. One walks a folder of markdown and updates the knowledge graph; act chapters line up by the number in their file name, while character chapters need no number. The other writes one chapter back out as markdown, either into the server's folder or to a path you name.

Use them when you need to load an existing manuscript, or rebuild a chapter file, without opening the editor. They use the same database settings as the API server.

## Missing settings

Both commands need `NEO4J_URL`, `NEO4J_USER`, and `NEO4J_PASSWORD` — from the environment or a
`.env` file — and the `en_core_web_sm` spaCy model. A variable that is absent or set to an empty
string, or a model that is not installed, is reported as a single `error:` line naming what is
missing, and the command exits 1. Nothing is opened or imported first, so a misconfigured shell
never reaches the database. `startup.py` owns that check for both commands; only a model that is
installed but broken is left to raise, since that is a real fault rather than a missing setting.

## Import a document directory

`python -m dockb.cli.import_document <document_dir> [--single-newline-paragraphs]` walks a
directory of markdown chapter files, diffing each against its chapter in the graph and persisting
changes. Each chapter file is matched through its front-matter `id`; changed or new files are
rewritten into the canonical span format (one identity span per paragraph). With
`--single-newline-paragraphs` each body line is read as a paragraph — for files whose paragraphs end
in a single newline and whose sentences run on inside a line — while the write-back stays canonical.
Chapters live only inside top-level `Act <name>` subdirectories — the act's name is its number
(digits, Roman numerals, or the Unicode single-character numerals), which orders the acts, with the
`Act None` directory holding the act-less chapters first — or in the reserved `Characters`
directory, imported last with no act and category `Character`. Root-level files and directories not
named `Act <name>` (and not named `Characters`) hold no chapters and are skipped. A chapter file's
act derives from its containing directory (used verbatim), which wins over any front-matter `act`;
a `Characters` file's category likewise wins over the front matter. The canonical write-back adds
the chapter's `category` to the front matter. Within an act each
file is imported in the order of the sequence number in its name — trailing at the end or embedded
between spaces — with at most one letter (5, 5a, 5b, 6; "Bad Guys Close In 48 Jael" → 48), and an
act file's name must carry that number. `Characters` files need no number: they import by file
name, and numbers in their names (or duplicated across them) are ignored. A file
that is not numbered in an act, two acts numbering the same, or two act files in one act
numbering the same abort the import. See
`../infrastructure/changes/README.md` for the diffing behavior.

## Reconstruct a chapter

`python -m dockb.cli.reconstruct_chapter <chapter_id> [--out PATH]` renders the chapter with
`chapter_id` from the knowledge graph as markdown. Without `--out` the canonical chapter file is
written into the server-owned tree — `<base>/<document title>/<Act X>/<chapter title>.md`, or
`<base>/<document title>/Characters/<chapter title>.md` for a `Character` chapter — under
`DOCKB_CHAPTERS_DIR` (defaulting to `cwd/dockb_chapters_dir`) — and git-committed; the written path
is printed. With `--out` it is written to the exact `PATH` instead, without touching the store tree.
A chapter id the graph does not know — or a chapter with no owning document (so it cannot be placed) —
prints the error message to stderr and exits non-zero. The serialization itself is the shared format
owned by `../infrastructure/markdown/`.