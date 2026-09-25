# DockB

## Executive Summary

DockB is a writing tool that stores each book as a knowledge graph
(Document → Chapter → Paragraph → Sentence → Token) in Neo4j, with a FastAPI
backend and spaCy for language analysis. Authors get structure a plain text
editor cannot: sentence splits, parts of speech, and a version history of every
chapter.

The desktop editor (`frontend/`) is a thin API client. Writers edit canonical
markdown in WYSIWYG or raw view; the editor never writes files or git. Hand
edits to the owned markdown files are absorbed the next time a chapter is
opened.

## Summary

### Front End

The front end is the part of DockB that a writer sees and types into: a desktop Electron app
with CodeMirror 6 (raw markdown) and ProseMirror (WYSIWYG) as two views of the same canonical
chapter. It is a thin API client — save and open go through
`GET/PUT /api/chapters/{id}/document`; app state and login live on the backend.

The backend's analysis of the text (sentence and word annotations) is embedded in the markdown
as spans, and the chapter's identity lives in the YAML front matter. The raw view shows the
canonical file exactly as stored. The WYSIWYG view shows only the body text: front matter and
span markup are hidden, and edits there save as loose body text that the backend re-imports into
canonical form.

Inside a span the sentence-delimiting newlines are read as a single space, so the sentences of
a paragraph flow and wrap together. A line ending in a backslash is an escape: the backslash is
hidden and the newline stays a line break. The double-newline paragraph delimiter renders as a
single line gap between paragraphs.

### Back End

The back end is where the manuscript's structure and meaning live. It is a FastAPI (Python) service backed by a Neo4j graph database, and it stores every manuscript as a hierarchy of Document, Chapter, Paragraph, Sentence, and Token nodes. Writing a sentence into the front end calls this service, which saves the node, then runs spaCy (a natural-language library) to split sentences, detect words, and assign grammatical roles. This analysis runs as a background job so the writer is not kept waiting; when it finishes, the results are queued and delivered back to the editor as notifications.

The back end also keeps a version history of each chapter. Every time a chapter changes, it writes a markdown snapshot committed to a local git repository, and the author can later list those snapshots or restore any one of them. The documentation under `src/dockb/` describes each layer of this service — the models, how data is stored and retrieved, the analysis jobs, and the API endpoints that tie it all together — and it is currently being reshaped around the redesign that makes markdown the single source of truth.

Every HTTP request also logs one INFO line (`src/dockb/timing.py`) with the total time and a per-stage breakdown, so a slow open shows exactly where the time went, e.g. `request GET /api/chapters/c1/document 200 220ms | repo.chapter.load 3ms, repo.chapter.find_document_id 1ms, repo.document.load 18ms, stage.apply_chapter_file 190ms, stage.git_commit 6ms, stage.read_chapter 2ms`. The stage names come from `measure()` calls in the service code; outside an HTTP request they are no-ops, so the backend behaves identically in unit tests and from the CLI.

## Further reading

- [`README_markdown_redesign.md`](README_markdown_redesign.md) — the markdown-based redesign decision and plan.
- Backend: [`src/dockb/controllers/README_API.md`](src/dockb/controllers/README_API.md) (API design), [`src/dockb/services/README.md`](src/dockb/services/README.md) (hydrators, reconstructors, jobs), [`src/dockb/services/semantics/README.md`](src/dockb/services/semantics/README.md), [`src/dockb/infrastructure/history/README.md`](src/dockb/infrastructure/history/README.md), [`src/dockb/models/README.md`](src/dockb/models/README.md), [`src/dockb/repositories/README.md`](src/dockb/repositories/README.md), [`src/dockb/cli/README.md`](src/dockb/cli/README.md) (command-line tools).
- Frontend: [`frontend/README.md`](frontend/README.md).
- Deferred work: [`README_todo.md`](README_todo.md) — a log of known-but-not-yet-done tasks
  discovered while building (e.g. the import HTTP endpoint), with pointers to the design docs
  for each.
- Development workflow: [`AGENTS.md`](AGENTS.md).

## Install

```bash
source .venv/bin/activate && pip install -e '.[dev]'
```

Run everything from the repo root. See [`AGENTS.md`](AGENTS.md) for backend checks (`make`), the dev server, and the frontend commands.
