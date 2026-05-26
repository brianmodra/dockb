# OpenCode Notes

## Documentaton

Design context is documented in README.md files under @src and @tests.
When modifying code, read all README.md files from @src (or @tests) down to the target file's directory,
in hierarchical order.

## Backend Commands
- Install dev deps from repo root: `source .venv/bin/activate && pip install -e '.[dev]'`.
- Backend checks: `source .venv/bin/activate && make` - it runs isort, mypy, pylint, black, ruff, pycycle, and pytest.
- Autofix/format before final checks when editing Python: `black src tests` and `ruff check --fix src tests`.
- Focused tests: e.g. `pytest tests/models/test_documents.py`

## Workflow Preferences
- Prefer test-driven changes and focused verification while editing.
- After user-approved edits, run relevant formatters, linters, type checks, and tests; fix failures you introduced. BTW just running `source .venv/bin/activate && make` will run all tests, and linters and will auto reformat.
- Favor readable, self-describing code over compact code or large explanatory comments.
