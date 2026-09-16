# README_todo.md — deferred work

## Purpose

This file is a running log of things we discover while developing DockB that have not been done
yet, but need to be done later. A hardware or design constraint may push them off, or they are
milestones behind the current work; either way they get noted here so nothing is forgotten. Each
entry names what is missing and points at the docs that describe the intended design. When an
entry is completed, delete it.

## Entries

- **OAuth login support** — `infrastructure/session/` is only stubs: `TokenValidator.validate`
  always returns `None`, `UserStore` does not exist, and `SessionManager`/`TokenValidator` are not
  wired into the app or any request middleware. There is no login flow, so no caller can yet
  identify the current user through the API. Design: `infrastructure/session/README.md`.
- **Import endpoint and composition wiring** — the directory walker
  (`services/markdown_import.py`) is driven today only by the command line
  (`python -m dockb.cli.import_document`); nothing in `controllers/` exposes it over HTTP and
  `composition.py` does not register it. Design: `infrastructure/changes/README.md`.
- **Friendly CLI errors** — `python -m dockb.cli.import_document` surfaces a raw `KeyError`
  traceback when `NEO4J_URL`/`NEO4J_USER`/`NEO4J_PASSWORD` are missing or unset. Print a
  one-line explanation instead.