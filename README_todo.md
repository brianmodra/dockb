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