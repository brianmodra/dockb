# README_todo.md — deferred work

## Executive Summary

This is a running list of DockB work that is known but not done yet. Each
entry says what is missing and points at the design doc for it. Delete an
entry when it is finished.

## Purpose

This file is a running log of things we discover while developing DockB that have not been done
yet, but need to be done later. A hardware or design constraint may push them off, or they are
milestones behind the current work; either way they get noted here so nothing is forgotten. Each
entry names what is missing and points at the docs that describe the intended design. When an
entry is completed, delete it.

## Entries

- **Import endpoint and composition wiring** — the directory walker
  (`services/markdown_import.py`) is driven today only by the command line
  (`python -m dockb.cli.import_document`); nothing in `controllers/` exposes it over HTTP and
  `composition.py` does not register it. Design: `infrastructure/changes/README.md`.
- **Friendly CLI errors** — `python -m dockb.cli.import_document` surfaces a raw `KeyError`
  traceback when `NEO4J_URL`/`NEO4J_USER`/`NEO4J_PASSWORD` are missing or unset. Print a
  one-line explanation instead.
- **Filesystem-unsafe titles pass the API** — a document or chapter title containing `/`, `\`,
  control characters, `.`/`..`, or the empty string satisfies the API schema (`title_not_blank`)
  but is rejected by `DocumentStore._validate_title`, so saving/opening it fails with a 500. The
  filesystem-safety rules should be enforced in the schema layer (→ 400) instead of only at file
  access. Design: `infrastructure/document_store/README.md`.
- **Title rename does not move owned files** — renaming a document's or chapter's title leaves the
  store tree keyed by the old title: the next open materializes a new title-keyed file while the
  old one stays (and a revert of the rename hydrates the stale file). A rename needs a `git mv` of
  the owning directory/file. Design: `README_markdown_redesign.md`, `infrastructure/document_store/README.md`.