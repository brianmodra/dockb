# OpenCode Notes

## Documentaton
- Design context lives in numbered files under `design_docs/`; read them in numeric order when changing domain behavior.

## Backend Commands
- Install dev deps from repo root: `source .venv/bin/activate && pip install -e '.[dev]'`.
- Backend checks: `black --check src tests`, `ruff check src tests`, `mypy src`, then `pytest`.
- Autofix/format before final checks when editing Python: `black src tests` and `ruff check --fix src tests`.
- Focused tests: e.g. `pytest tests/models/test_documents.py`

## Workflow Preferences
- Prefer test-driven changes and focused verification while editing.
- After user-approved edits, run relevant formatters, linters, type checks, and tests; fix failures you introduced.
- Favor readable, self-describing code over compact code or large explanatory comments.
