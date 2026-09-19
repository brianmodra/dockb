# Command-line interfaces

Command-line entry points for DockB, run as Python modules. Both connect to Neo4j with the same
`NEO4J_URL`, `NEO4J_USER`, `NEO4J_PASSWORD` environment variables (or `.env`) the API server uses.

## Import a document directory

`python -m dockb.cli.import_document <document_dir>` walks a directory of markdown chapter files,
diffing each against its chapter in the graph and persisting changes. Each chapter file is matched
through its front-matter `id`; changed or new files are rewritten into the canonical span format.
See `../infrastructure/changes/README.md` for the diffing behavior.

## Reconstruct a chapter

`python -m dockb.cli.reconstruct_chapter <chapter_id> [--out PATH]` renders the chapter with
`chapter_id` from the knowledge graph as markdown. Without `--out` the canonical chapter file
(front matter plus one identity span per sentence) is printed to stdout; with `--out` it is written
to `PATH`. A chapter id the graph does not know prints the error message to stderr and exits
non-zero. The serialization itself is the shared format owned by `../infrastructure/markdown/`.