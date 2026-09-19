# DockB

## Executive Summary

DockB is a writing tool that treats every book as a knowledge graph: each document is stored as a strict hierarchy of Document → Chapter → Paragraph → Sentence → Token in a Neo4j graph database. A FastAPI backend exposes a REST API for this hierarchy and uses spaCy to tokenize sentences (POS, lemmas, etc.) and to detect sentence and paragraph splits as the text changes. Its purpose is to give authors rich, language-aware structure over their manuscripts that a plain text editor cannot.

The front end treats the markdown file (one per chapter) as the single source of truth. An author edits a plain markdown file with whatever editor they like while the backend stays in step. (Later a custom MD editor will be created as a more slick FE.) A "sync engine" process watches the file, detects what changed, and calls the backend to refresh the knowledge graph before the writer continues.

## Summary

### Front End

The front end is the part of DockB that a writer sees and types into. It is a desktop writing app (custom markdown editor) with the markdown file as the single source of truth. The writer types in a flat markdown editor — CodeMirror 6 for the source view, with a normal rendered view layered on top — so editing behaves like any familiar plain-text tool.

The backend's analysis of the text (sentence and word annotations) is embedded directly in the markdown as spans, and the front end's job is only to render those spans as styled highlights. Because the analysis lives in the text itself, the editor stays a simple markdown surface and the two pieces never go out of step.

### Back End

The back end is where the manuscript's structure and meaning live. It is a FastAPI (Python) service backed by a Neo4j graph database, and it stores every manuscript as a hierarchy of Document, Chapter, Paragraph, Sentence, and Token nodes. Writing a sentence into the front end calls this service, which saves the node, then runs spaCy (a natural-language library) to split sentences, detect words, and assign grammatical roles. This analysis runs as a background job so the writer is not kept waiting; when it finishes, the results are queued and delivered back to the editor as notifications.

The back end also keeps a version history of each chapter. Every time a chapter changes, it writes a markdown snapshot committed to a local git repository, and the author can later list those snapshots or restore any one of them. The documentation under `src/dockb/` describes each layer of this service — the models, how data is stored and retrieved, the analysis jobs, and the API endpoints that tie it all together — and it is currently being reshaped around the redesign that makes markdown the single source of truth.

## Further reading

- [`README_markdown_redesign.md`](README_markdown_redesign.md) — the markdown-based redesign decision and plan.
- Backend: [`src/dockb/controllers/README_API.md`](src/dockb/controllers/README_API.md) (API design), [`src/dockb/services/README.md`](src/dockb/services/README.md) (hydrators, reconstructors, jobs), [`src/dockb/services/semantics/README.md`](src/dockb/services/semantics/README.md), [`src/dockb/infrastructure/history/README.md`](src/dockb/infrastructure/history/README.md), [`src/dockb/models/README.md`](src/dockb/models/README.md), [`src/dockb/repositories/README.md`](src/dockb/repositories/README.md), [`src/dockb/cli/README.md`](src/dockb/cli/README.md) (command-line tools).
- Frontend: [`frontend/README.md`](frontend/README.md).
- Deferred work: [`README_todo.md`](README_todo.md) — a log of known-but-not-yet-done tasks
  discovered while building (e.g. OAuth login, the import HTTP endpoint), with pointers to the
  design docs for each.
- Development workflow: [`AGENTS.md`](AGENTS.md).

## Install

```bash
source .venv/bin/activate && pip install -e '.[dev]'
```

Run everything from the repo root. See [`AGENTS.md`](AGENTS.md) for backend checks (`make`), the dev server, and the frontend commands.
